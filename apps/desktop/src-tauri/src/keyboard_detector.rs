//! Physical keyboard detection for the register.
//!
//! Windows enumerates HID keyboards through the raw-input list, which is how a wired USB keyboard, a
//! Surface Type Cover, and a connected Bluetooth keyboard all show up. Paired-but-disconnected radios do
//! not appear. Virtual drivers (the Windows on-screen keyboard, Remote Desktop, hypervisors) are excluded.

use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ConnectionType {
    Wired,
    Bluetooth,
    SurfaceCover,
    None,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct KeyboardStatus {
    pub has_physical_keyboard: bool,
    pub connection_type: ConnectionType,
    pub is_touch_device: bool,
}

impl KeyboardStatus {
    fn absent(is_touch_device: bool) -> Self {
        Self {
            has_physical_keyboard: false,
            connection_type: ConnectionType::None,
            is_touch_device,
        }
    }
}

/// Microsoft Surface Type Cover product ids (vendor 0x045E). The pogo-pin cover enumerates as USB HID.
const SURFACE_COVER_PIDS: &[u16] = &[
    0x07CD, 0x07DE, 0x07E2, 0x07E6, 0x07E8, 0x09AE, 0x09C0, 0x0A1B, 0x0B12, 0x0C1A,
];

const VIRTUAL_MARKERS: &[&str] = &[
    "root#",
    "rdp",
    "terminput",
    "virtual",
    "vmware",
    "vbox",
    "qemu",
    "osk",
    "loopback",
    "miracast",
    "remote desktop",
];

/// `None` when the device path is a software keyboard. Otherwise the physical link it uses.
pub fn classify_device_name(name: &str) -> Option<ConnectionType> {
    let lower = name.to_ascii_lowercase();
    if lower.trim().is_empty() || VIRTUAL_MARKERS.iter().any(|marker| lower.contains(marker)) {
        return None;
    }
    if lower.contains("bthenum") || lower.contains("bthle") || lower.contains("bluetooth") || lower.contains("&bth")
    {
        return Some(ConnectionType::Bluetooth);
    }
    if is_surface_cover(&lower) {
        return Some(ConnectionType::SurfaceCover);
    }
    Some(ConnectionType::Wired)
}

fn is_surface_cover(lower: &str) -> bool {
    if lower.contains("surface") || lower.contains("type cover") || lower.contains("type_cover") || lower.contains("pogopin")
    {
        return true;
    }
    let Some((vid, pid)) = vid_pid(lower) else {
        return false;
    };
    vid == 0x045E && SURFACE_COVER_PIDS.contains(&pid)
}

fn vid_pid(lower: &str) -> Option<(u16, u16)> {
    let vid_at = lower.find("vid_")?;
    let pid_at = lower.find("pid_")?;
    let vid = u16::from_str_radix(lower.get(vid_at + 4..vid_at + 8)?, 16).ok()?;
    let pid = u16::from_str_radix(lower.get(pid_at + 4..pid_at + 8)?, 16).ok()?;
    Some((vid, pid))
}

fn prefer(current: ConnectionType, next: ConnectionType) -> ConnectionType {
    fn rank(kind: ConnectionType) -> u8 {
        match kind {
            ConnectionType::Wired => 3,
            ConnectionType::SurfaceCover => 2,
            ConnectionType::Bluetooth => 1,
            ConnectionType::None => 0,
        }
    }
    if rank(next) > rank(current) { next } else { current }
}

pub fn status_from_names(names: &[String], is_touch_device: bool) -> KeyboardStatus {
    let mut connection = ConnectionType::None;
    for name in names {
        if let Some(kind) = classify_device_name(name) {
            connection = prefer(connection, kind);
        }
    }
    if connection == ConnectionType::None {
        KeyboardStatus::absent(is_touch_device)
    } else {
        KeyboardStatus {
            has_physical_keyboard: true,
            connection_type: connection,
            is_touch_device,
        }
    }
}

#[cfg(windows)]
mod platform {
    use std::ffi::OsString;
    use std::os::windows::ffi::OsStringExt;
    use std::sync::Mutex;
    use std::thread;

    use tauri::{AppHandle, Emitter};
    use windows_sys::Win32::Devices::HumanInterfaceDevice::HidD_GetProductString;
    use windows_sys::Win32::Foundation::{CloseHandle, GetLastError, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::{
        CreateFileW, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING,
    };
    use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
    use windows_sys::Win32::UI::Input::{
        GetRawInputDeviceInfoW, GetRawInputDeviceList, RegisterRawInputDevices, RAWINPUTDEVICE,
        RAWINPUTDEVICELIST, RIDI_DEVICENAME, RIM_TYPEKEYBOARD,
    };
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        CreateWindowExW, DefWindowProcW, DispatchMessageW,         GetMessageW, GetSystemMetrics, KillTimer, RegisterClassW, RegisterDeviceNotificationW, SetTimer,
        TranslateMessage, HDEVNOTIFY, HWND_MESSAGE, MSG, SM_DIGITIZER, SM_MAXIMUMTOUCHES, WM_DEVICECHANGE,
        WM_TIMER, WNDCLASSW, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW,
    };

    use super::{status_from_names, KeyboardStatus};

    const RIDEV_DEVNOTIFY: u32 = 0x0000_2000;
    const WM_INPUT_DEVICE_CHANGE: u32 = 0x00FE;
    const NID_INTEGRATED_TOUCH: i32 = 0x01;
    const GENERIC_READ: u32 = 0x8000_0000;
    const DBT_DEVICEARRIVAL: u32 = 0x8000;
    const DBT_DEVICEREMOVECOMPLETE: u32 = 0x8004;
    const DBT_DEVNODES_CHANGED: u32 = 0x0007;
    const DEVICE_NOTIFY_WINDOW_HANDLE: u32 = 0;
    const DBT_DEVTYP_DEVICEINTERFACE: u32 = 5;
    const TIMER_RESCAN: usize = 1;

    /// Bluetooth radio device interface and the HID class, so a cover or a paired keyboard wakes the scan.
    const GUID_BTHPORT: windows_sys::core::GUID = windows_sys::core::GUID {
        data1: 0x0850_302A,
        data2: 0xB344,
        data3: 0x4FDA,
        data4: [0x9B, 0xE9, 0x90, 0x57, 0x6B, 0x8D, 0x46, 0xF0],
    };
    const GUID_DEVINTERFACE_HID: windows_sys::core::GUID = windows_sys::core::GUID {
        data1: 0x4D1E_55B2,
        data2: 0xF16F,
        data3: 0x11CF,
        data4: [0x88, 0xCB, 0x00, 0x11, 0x11, 0x00, 0x00, 0x30],
    };

    #[repr(C)]
    struct DeviceInterface {
        size: u32,
        device_type: u32,
        reserved: u32,
        class_guid: windows_sys::core::GUID,
        name: u16,
    }

    static LAST: Mutex<Option<KeyboardStatus>> = Mutex::new(None);
    static APP: Mutex<Option<AppHandle>> = Mutex::new(None);

    pub fn current() -> KeyboardStatus {
        let touch = is_touch_device();
        let names = keyboard_names();
        status_from_names(&names, touch)
    }

    pub fn start(app: AppHandle) {
        if APP.lock().ok().and_then(|guard| guard.as_ref().map(|_| ())).is_some() {
            return;
        }
        if let Ok(mut guard) = APP.lock() {
            *guard = Some(app);
        }
        thread::Builder::new()
            .name("keyboard-detector".into())
            .spawn(message_loop)
            .ok();
    }

    fn is_touch_device() -> bool {
        unsafe {
            GetSystemMetrics(SM_MAXIMUMTOUCHES) > 0
                || (GetSystemMetrics(SM_DIGITIZER) & NID_INTEGRATED_TOUCH) != 0
        }
    }

    fn keyboard_names() -> Vec<String> {
        unsafe {
            let mut count = 0u32;
            let size = std::mem::size_of::<RAWINPUTDEVICELIST>() as u32;
            if GetRawInputDeviceList(std::ptr::null_mut(), &mut count, size) == u32::MAX || count == 0 {
                return Vec::new();
            }
            let mut devices = vec![
                RAWINPUTDEVICELIST {
                    hDevice: std::ptr::null_mut(),
                    dwType: 0,
                };
                count as usize
            ];
            let written = GetRawInputDeviceList(devices.as_mut_ptr(), &mut count, size);
            if written == u32::MAX {
                return Vec::new();
            }
            devices.truncate(written as usize);
            devices
                .into_iter()
                .filter(|device| device.dwType == RIM_TYPEKEYBOARD)
                .filter_map(|device| device_name(device.hDevice))
                .collect()
        }
    }

    unsafe fn device_name(handle: windows_sys::Win32::Foundation::HANDLE) -> Option<String> {
        let mut bytes = 0u32;
        if GetRawInputDeviceInfoW(handle, RIDI_DEVICENAME, std::ptr::null_mut(), &mut bytes) == u32::MAX || bytes == 0
        {
            return None;
        }
        let mut wide = vec![0u16; bytes as usize];
        let written = GetRawInputDeviceInfoW(
            handle,
            RIDI_DEVICENAME,
            wide.as_mut_ptr().cast(),
            &mut bytes,
        );
        if written == u32::MAX {
            return None;
        }
        let end = wide.iter().position(|unit| *unit == 0).unwrap_or(wide.len());
        let path = OsString::from_wide(&wide[..end]).to_string_lossy().into_owned();
        let product = product_string(&path);
        if product.is_empty() {
            Some(path)
        } else {
            Some(format!("{path} {product}"))
        }
    }

    unsafe fn product_string(path: &str) -> String {
        let wide: Vec<u16> = path.encode_utf16().chain(std::iter::once(0)).collect();
        let handle = CreateFileW(
            wide.as_ptr(),
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            std::ptr::null(),
            OPEN_EXISTING,
            0,
            std::ptr::null_mut(),
        );
        if handle == INVALID_HANDLE_VALUE {
            return String::new();
        }
        let mut name = [0u16; 126];
        let ok = HidD_GetProductString(handle, name.as_mut_ptr().cast(), (name.len() * 2) as u32);
        CloseHandle(handle);
        if !ok {
            let _ = GetLastError();
            return String::new();
        }
        let end = name.iter().position(|unit| *unit == 0).unwrap_or(name.len());
        OsString::from_wide(&name[..end]).to_string_lossy().into_owned()
    }

    fn publish() {
        let status = current();
        let changed = APP
            .lock()
            .ok()
            .zip(LAST.lock().ok())
            .and_then(|(app, mut last)| {
                if last.as_ref() == Some(&status) {
                    return None;
                }
                *last = Some(status);
                app.clone()
            });
        if let Some(app) = changed {
            let _ = app.emit("keyboard-hardware-change", status);
        }
    }

    fn message_loop() {
        unsafe {
            let class_name: Vec<u16> = "AiPosKeyboardDetector\0".encode_utf16().collect();
            let class = WNDCLASSW {
                style: 0,
                lpfnWndProc: Some(wndproc),
                cbClsExtra: 0,
                cbWndExtra: 0,
                hInstance: GetModuleHandleW(std::ptr::null()),
                hIcon: std::ptr::null_mut(),
                hCursor: std::ptr::null_mut(),
                hbrBackground: std::ptr::null_mut(),
                lpszMenuName: std::ptr::null(),
                lpszClassName: class_name.as_ptr(),
            };
            if RegisterClassW(&class) == 0 {
                eprintln!("ai-pos: keyboard detector window class was not registered");
                return;
            }
            let hwnd = CreateWindowExW(
                WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
                class_name.as_ptr(),
                class_name.as_ptr(),
                0,
                0,
                0,
                0,
                0,
                HWND_MESSAGE,
                std::ptr::null_mut(),
                class.hInstance,
                std::ptr::null(),
            );
            if hwnd.is_null() {
                eprintln!("ai-pos: keyboard detector window was not created");
                return;
            }
            let device = RAWINPUTDEVICE {
                usUsagePage: 0x01,
                usUsage: 0x06,
                dwFlags: RIDEV_DEVNOTIFY,
                hwndTarget: hwnd,
            };
            if RegisterRawInputDevices(&device, 1, std::mem::size_of::<RAWINPUTDEVICE>() as u32) == 0 {
                eprintln!("ai-pos: raw keyboard device notifications were not registered");
            }
            let _hid = register_interface(hwnd, GUID_DEVINTERFACE_HID);
            let _bluetooth = register_interface(hwnd, GUID_BTHPORT);
            publish();
            let mut message = MSG {
                hwnd: std::ptr::null_mut(),
                message: 0,
                wParam: 0,
                lParam: 0,
                time: 0,
                pt: windows_sys::Win32::Foundation::POINT { x: 0, y: 0 },
            };
            while GetMessageW(&mut message, hwnd, 0, 0) > 0 {
                TranslateMessage(&message);
                DispatchMessageW(&message);
            }
        }
    }

    unsafe fn register_interface(
        hwnd: windows_sys::Win32::Foundation::HWND,
        guid: windows_sys::core::GUID,
    ) -> HDEVNOTIFY {
        let filter = DeviceInterface {
            size: std::mem::size_of::<DeviceInterface>() as u32,
            device_type: DBT_DEVTYP_DEVICEINTERFACE,
            reserved: 0,
            class_guid: guid,
            name: 0,
        };
        RegisterDeviceNotificationW(
            hwnd as *mut _,
            &filter as *const DeviceInterface as *const _,
            DEVICE_NOTIFY_WINDOW_HANDLE,
        )
    }

    unsafe extern "system" fn wndproc(
        hwnd: windows_sys::Win32::Foundation::HWND,
        message: u32,
        wparam: windows_sys::Win32::Foundation::WPARAM,
        lparam: windows_sys::Win32::Foundation::LPARAM,
    ) -> windows_sys::Win32::Foundation::LRESULT {
        let rescan = message == WM_INPUT_DEVICE_CHANGE
            || (message == WM_DEVICECHANGE
                && matches!(
                    wparam as u32,
                    DBT_DEVICEARRIVAL | DBT_DEVICEREMOVECOMPLETE | DBT_DEVNODES_CHANGED
                ));
        if rescan {
            SetTimer(hwnd, TIMER_RESCAN, 400, None);
            return 0;
        }
        if message == WM_TIMER && wparam == TIMER_RESCAN {
            KillTimer(hwnd, TIMER_RESCAN);
            publish();
            return 0;
        }
        DefWindowProcW(hwnd, message, wparam, lparam)
    }

}

#[cfg(not(windows))]
mod platform {
    use tauri::AppHandle;

    use super::{ConnectionType, KeyboardStatus};

    pub fn current() -> KeyboardStatus {
        KeyboardStatus {
            has_physical_keyboard: true,
            connection_type: ConnectionType::Wired,
            is_touch_device: false,
        }
    }

    pub fn start(_app: AppHandle) {}
}

#[tauri::command]
pub fn check_hardware_keyboard_status() -> KeyboardStatus {
    platform::current()
}

pub fn start(app: tauri::AppHandle) {
    platform::start(app);
}

#[cfg(test)]
mod tests {
    use super::{classify_device_name, status_from_names, ConnectionType};

    #[test]
    fn virtual_drivers_are_not_physical_keyboards() {
        assert_eq!(classify_device_name(r"\\?\ROOT#RDP_KBD#0000#{guid}"), None);
        assert_eq!(classify_device_name(r"\\?\HID#VIRTUALKEYBOARD&Col01"), None);
        assert_eq!(classify_device_name(r"\\?\HID#VID_0E0F&PID_0003#VMware"), None);
    }

    #[test]
    fn usb_bluetooth_and_surface_covers_are_distinct() {
        assert_eq!(
            classify_device_name(r"\\?\HID#VID_046D&PID_C31C&MI_00#7&abc&0&0000#{guid}"),
            Some(ConnectionType::Wired)
        );
        assert_eq!(
            classify_device_name(r"\\?\BTHENUM#{00001124-0000-1000-8000-00805f9b34fb}"),
            Some(ConnectionType::Bluetooth)
        );
        assert_eq!(
            classify_device_name(r"\\?\HID#VID_045E&PID_09C0&MI_00#type cover"),
            Some(ConnectionType::SurfaceCover)
        );
    }

    #[test]
    fn a_wired_keyboard_outranks_a_cover_and_virtual_devices_do_not_count() {
        let status = status_from_names(
            &[
                r"\\?\ROOT#SYSTEM#0000".into(),
                r"\\?\BTHENUM#keyboard".into(),
                r"\\?\HID#VID_046D&PID_C52B".into(),
            ],
            true,
        );
        assert!(status.has_physical_keyboard);
        assert_eq!(status.connection_type, ConnectionType::Wired);
        assert!(status.is_touch_device);
        let bare = status_from_names(&[r"\\?\ROOT#RDP_KBD".into()], true);
        assert!(!bare.has_physical_keyboard);
        assert_eq!(bare.connection_type, ConnectionType::None);
    }
}
