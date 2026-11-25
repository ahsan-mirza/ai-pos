//! Native full-screen for the main register window.
//!
//! Every launch enters full-screen after the window exists. Leaving full-screen lasts only until
//! the process exits: the choice is kept in memory and is not written as a startup preference.
//! Full-screen is Tauri borderless full-screen (`set_fullscreen`), not kiosk mode and not a
//! display-mode change. Alt+F4, the taskbar, and Task Manager stay available.

use std::sync::{Mutex, MutexGuard, TryLockError};

use tauri::{AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, WebviewWindow, WindowEvent};

const MIN_SPAN: i64 = 64;
const CONFIGURED_WIDTH: f64 = 1440.0;
const CONFIGURED_HEIGHT: f64 = 900.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Frame {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct MonitorArea {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ScreenState {
    pub fullscreen: bool,
    pub windowed: Frame,
    pub maximized: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Request {
    Enter,
    Exit,
    Toggle,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Restore {
    pub frame: Frame,
    pub maximized: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Planned {
    pub fullscreen: bool,
    pub decorations: bool,
    pub restore: Option<Restore>,
    pub unchanged: bool,
}

/// Full-screen is applied on launch whether or not the API can be reached.
pub fn startup_fullscreen(api_reachable: bool) -> bool {
    let _ = api_reachable;
    true
}

/// Windowed use is session-only. Nothing is stored for the next launch.
pub fn persisted_windowed_preference() -> Option<&'static str> {
    None
}

pub fn launch_state(windowed: Frame) -> ScreenState {
    ScreenState {
        fullscreen: true,
        windowed,
        maximized: false,
    }
}

pub fn plan(
    state: &mut ScreenState,
    request: Request,
    monitors: &[MonitorArea],
    preferred: Option<MonitorArea>,
    native_ok: bool,
) -> Result<Planned, String> {
    let want = match request {
        Request::Enter => true,
        Request::Exit => false,
        Request::Toggle => !state.fullscreen,
    };
    if want == state.fullscreen {
        return Ok(Planned {
            fullscreen: state.fullscreen,
            decorations: !state.fullscreen,
            restore: None,
            unchanged: true,
        });
    }
    if !native_ok {
        state.fullscreen = false;
        return Err("The window could not change screen mode. The register stayed in a normal window.".into());
    }
    if want {
        state.fullscreen = true;
        return Ok(Planned {
            fullscreen: true,
            decorations: false,
            restore: None,
            unchanged: false,
        });
    }
    let frame = restore_target(state.windowed, monitors, preferred);
    state.fullscreen = false;
    Ok(Planned {
        fullscreen: false,
        decorations: true,
        restore: Some(Restore {
            frame,
            maximized: state.maximized,
        }),
        unchanged: false,
    })
}

pub fn restore_target(saved: Frame, monitors: &[MonitorArea], preferred: Option<MonitorArea>) -> Frame {
    if monitors.is_empty() {
        return saved;
    }
    if monitors.iter().any(|monitor| contained(saved, *monitor)) {
        return saved;
    }
    if frame_visible(saved, monitors) {
        let monitor = best_overlap(saved, monitors).unwrap_or(monitors[0]);
        return fit_inside(saved, monitor);
    }
    let monitor = preferred
        .filter(|area| monitors.iter().any(|candidate| candidate == area))
        .unwrap_or(monitors[0]);
    place_on_monitor(saved, monitor)
}

pub fn frame_visible(frame: Frame, monitors: &[MonitorArea]) -> bool {
    monitors.iter().any(|monitor| {
        overlap_len(frame.x, frame.width, monitor.x, monitor.width) >= MIN_SPAN
            && overlap_len(frame.y, frame.height, monitor.y, monitor.height) >= MIN_SPAN
    })
}

pub fn contained(frame: Frame, monitor: MonitorArea) -> bool {
    let right = frame.x as i64 + frame.width as i64;
    let bottom = frame.y as i64 + frame.height as i64;
    let monitor_right = monitor.x as i64 + monitor.width as i64;
    let monitor_bottom = monitor.y as i64 + monitor.height as i64;
    frame.x as i64 >= monitor.x as i64
        && frame.y as i64 >= monitor.y as i64
        && right <= monitor_right
        && bottom <= monitor_bottom
        && frame.width > 0
        && frame.height > 0
}

fn fit_inside(frame: Frame, monitor: MonitorArea) -> Frame {
    let width = frame.width.min(monitor.width.max(1));
    let height = frame.height.min(monitor.height.max(1));
    let min_x = monitor.x as i64;
    let min_y = monitor.y as i64;
    let max_x = monitor.x as i64 + monitor.width as i64 - width as i64;
    let max_y = monitor.y as i64 + monitor.height as i64 - height as i64;
    Frame {
        x: (frame.x as i64).clamp(min_x, max_x) as i32,
        y: (frame.y as i64).clamp(min_y, max_y) as i32,
        width,
        height,
    }
}

pub fn place_on_monitor(frame: Frame, monitor: MonitorArea) -> Frame {
    let fitted = fit_inside(frame, monitor);
    let x = monitor.x as i64 + (monitor.width as i64 - fitted.width as i64) / 2;
    let y = monitor.y as i64 + (monitor.height as i64 - fitted.height as i64) / 2;
    Frame {
        x: x as i32,
        y: y as i32,
        width: fitted.width,
        height: fitted.height,
    }
}

fn best_overlap(frame: Frame, monitors: &[MonitorArea]) -> Option<MonitorArea> {
    monitors
        .iter()
        .copied()
        .max_by_key(|monitor| {
            overlap_len(frame.x, frame.width, monitor.x, monitor.width)
                * overlap_len(frame.y, frame.height, monitor.y, monitor.height)
        })
}

fn overlap_len(origin: i32, length: u32, monitor_origin: i32, monitor_length: u32) -> i64 {
    let start = origin as i64;
    let end = origin as i64 + length as i64;
    let monitor_start = monitor_origin as i64;
    let monitor_end = monitor_origin as i64 + monitor_length as i64;
    (end.min(monitor_end) - start.max(monitor_start)).max(0)
}

struct ScreenController {
    windowed: Mutex<Frame>,
    maximized: Mutex<bool>,
    busy: Mutex<()>,
    published: Mutex<Option<bool>>,
}

impl Default for ScreenController {
    fn default() -> Self {
        Self {
            windowed: Mutex::new(Frame {
                x: 80,
                y: 80,
                width: CONFIGURED_WIDTH as u32,
                height: CONFIGURED_HEIGHT as u32,
            }),
            maximized: Mutex::new(false),
            busy: Mutex::new(()),
            published: Mutex::new(None),
        }
    }
}

impl ScreenController {
    fn try_begin(&self) -> Result<MutexGuard<'_, ()>, String> {
        match self.busy.try_lock() {
            Ok(guard) => Ok(guard),
            Err(TryLockError::WouldBlock) => Err("A screen change is already in progress.".into()),
            Err(TryLockError::Poisoned(err)) => Ok(err.into_inner()),
        }
    }

    fn snapshot(&self) -> ScreenState {
        ScreenState {
            fullscreen: false,
            windowed: *lock(&self.windowed),
            maximized: *lock(&self.maximized),
        }
    }

    fn store(&self, state: &ScreenState) {
        *lock(&self.windowed) = state.windowed;
        *lock(&self.maximized) = state.maximized;
    }
}

fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|err| err.into_inner())
}

/// Hides the window, enters native full-screen, then shows it. A failure leaves a decorated window.
pub fn start(app: &AppHandle) -> Result<(), String> {
    app.manage(ScreenController::default());
    let Some(window) = app.get_webview_window("main") else {
        return Err("The main register window is missing.".into());
    };
    let handle = app.clone();
    window.on_window_event(move |event| {
        if !matches!(event, WindowEvent::Resized(_) | WindowEvent::ScaleFactorChanged { .. }) {
            return;
        }
        sync_published(&handle);
    });
    let _ = window.hide();
    let outcome = change(app, Request::Enter);
    if let Err(message) = window.show() {
        eprintln!("ai-pos: the register window could not be shown: {message}");
    }
    let _ = window.set_focus();
    outcome.map(|_| ())
}

#[tauri::command]
pub fn window_fullscreen_state(app: AppHandle) -> Result<bool, String> {
    let window = main_window(&app)?;
    window.is_fullscreen().map_err(|err| err.to_string())
}

#[tauri::command]
pub fn window_set_fullscreen(app: AppHandle, fullscreen: bool) -> Result<bool, String> {
    change(&app, if fullscreen { Request::Enter } else { Request::Exit })
}

#[tauri::command]
pub fn window_toggle_fullscreen(app: AppHandle) -> Result<bool, String> {
    change(&app, Request::Toggle)
}

fn main_window(app: &AppHandle) -> Result<WebviewWindow, String> {
    app.get_webview_window("main")
        .ok_or_else(|| "The main register window is missing.".to_string())
}

fn change(app: &AppHandle, request: Request) -> Result<bool, String> {
    let window = main_window(app)?;
    let controller = app
        .try_state::<ScreenController>()
        .ok_or_else(|| "Screen mode is not ready.".to_string())?;
    let _guard = controller.try_begin()?;
    let mut state = controller.snapshot();
    remember_windowed(&window, &mut state);
    state.fullscreen = window.is_fullscreen().unwrap_or(false);
    let monitors = monitor_areas(&window);
    let preferred = current_area(&window);
    let planned = match plan(&mut state, request, &monitors, preferred, true) {
        Ok(planned) => planned,
        Err(message) => {
            recover_windowed(&window, controller.inner(), &mut state);
            return Err(message);
        }
    };
    if let Err(message) = execute(&window, &planned) {
        recover_windowed(&window, controller.inner(), &mut state);
        return Err(message);
    }
    controller.store(&state);
    let actual = window.is_fullscreen().unwrap_or(state.fullscreen);
    publish(&window, actual, controller.inner());
    Ok(actual)
}

fn remember_windowed(window: &WebviewWindow, state: &mut ScreenState) {
    if window.is_fullscreen().unwrap_or(false) {
        return;
    }
    let maximized = window.is_maximized().unwrap_or(false);
    state.maximized = maximized;
    if maximized {
        return;
    }
    if let Some(frame) = read_frame(window) {
        state.windowed = frame;
    } else {
        state.windowed = default_frame(window);
    }
}

fn recover_windowed(window: &WebviewWindow, controller: &ScreenController, state: &mut ScreenState) {
    fallback_windowed(window);
    state.fullscreen = false;
    controller.store(state);
    publish(window, false, controller);
}

fn fallback_windowed(window: &WebviewWindow) {
    let _ = window.set_fullscreen(false);
    let _ = window.set_decorations(true);
}

fn execute(window: &WebviewWindow, planned: &Planned) -> Result<(), String> {
    if planned.unchanged {
        return Ok(());
    }
    if planned.fullscreen {
        if let Err(err) = window.set_decorations(false) {
            eprintln!("ai-pos: the title bar could not be hidden: {err}");
        }
        window.set_fullscreen(true).map_err(|err| err.to_string())?;
        if !window.is_fullscreen().unwrap_or(false) {
            fallback_windowed(window);
            return Err("Full screen did not start. The register stayed in a normal window.".into());
        }
        return Ok(());
    }
    window.set_decorations(true).map_err(|err| err.to_string())?;
    window.set_fullscreen(false).map_err(|err| err.to_string())?;
    if let Some(restore) = planned.restore {
        let _ = window.unmaximize();
        if restore.maximized {
            window.maximize().map_err(|err| err.to_string())?;
        } else {
            window
                .set_size(PhysicalSize::new(restore.frame.width, restore.frame.height))
                .map_err(|err| err.to_string())?;
            window
                .set_position(PhysicalPosition::new(restore.frame.x, restore.frame.y))
                .map_err(|err| err.to_string())?;
        }
    }
    Ok(())
}

fn read_frame(window: &WebviewWindow) -> Option<Frame> {
    let position = window.outer_position().ok()?;
    let size = window.outer_size().ok()?;
    if size.width < 320 || size.height < 240 {
        return None;
    }
    Some(Frame {
        x: position.x,
        y: position.y,
        width: size.width,
        height: size.height,
    })
}

fn default_frame(window: &WebviewWindow) -> Frame {
    let scale = window.scale_factor().unwrap_or(1.0).max(1.0);
    let frame = Frame {
        x: 80,
        y: 80,
        width: (CONFIGURED_WIDTH * scale).round() as u32,
        height: (CONFIGURED_HEIGHT * scale).round() as u32,
    };
    match current_area(window) {
        Some(area) => place_on_monitor(frame, area),
        None => frame,
    }
}

fn monitor_areas(window: &WebviewWindow) -> Vec<MonitorArea> {
    window
        .available_monitors()
        .unwrap_or_default()
        .iter()
        .map(area_from)
        .collect()
}

fn current_area(window: &WebviewWindow) -> Option<MonitorArea> {
    window.current_monitor().ok().flatten().as_ref().map(area_from)
}

fn area_from(monitor: &tauri::Monitor) -> MonitorArea {
    let work = monitor.work_area();
    if work.size.width > 0 && work.size.height > 0 {
        MonitorArea {
            x: work.position.x,
            y: work.position.y,
            width: work.size.width,
            height: work.size.height,
        }
    } else {
        MonitorArea {
            x: monitor.position().x,
            y: monitor.position().y,
            width: monitor.size().width,
            height: monitor.size().height,
        }
    }
}

fn publish(window: &WebviewWindow, fullscreen: bool, controller: &ScreenController) {
    let mut published = lock(&controller.published);
    if *published == Some(fullscreen) {
        return;
    }
    *published = Some(fullscreen);
    drop(published);
    let _ = window.emit("pos-fullscreen-changed", fullscreen);
}

fn sync_published(app: &AppHandle) {
    let Some(controller) = app.try_state::<ScreenController>() else {
        return;
    };
    let Ok(_guard) = controller.try_begin() else {
        return;
    };
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let Ok(fullscreen) = window.is_fullscreen() else {
        return;
    };
    drop(_guard);
    publish(&window, fullscreen, controller.inner());
}

#[cfg(test)]
mod tests {
    use super::*;

    fn desktop() -> MonitorArea {
        MonitorArea {
            x: 0,
            y: 0,
            width: 1920,
            height: 1040,
        }
    }

    fn original() -> Frame {
        Frame {
            x: 120,
            y: 80,
            width: 1440,
            height: 900,
        }
    }

    #[test]
    fn startup_is_fullscreen_without_the_api_and_without_a_saved_preference() {
        assert!(startup_fullscreen(false));
        assert!(startup_fullscreen(true));
        assert!(persisted_windowed_preference().is_none());
        let launched = launch_state(original());
        assert!(launched.fullscreen);
        assert_eq!(launched.windowed, original());
    }

    #[test]
    fn relaunch_returns_to_fullscreen_instead_of_the_last_windowed_session() {
        let monitors = [desktop()];
        let mut session = launch_state(original());
        plan(&mut session, Request::Exit, &monitors, None, true).unwrap();
        session.windowed = Frame {
            x: 400,
            y: 200,
            width: 800,
            height: 600,
        };
        assert!(!session.fullscreen);
        let next = launch_state(original());
        assert!(next.fullscreen);
        assert_eq!(next.windowed, original());
        assert_ne!(next.windowed, session.windowed);
    }

    #[test]
    fn enter_exit_and_toggle_keep_the_windowed_frame() {
        let monitors = [desktop()];
        let mut state = launch_state(original());
        let exit = plan(&mut state, Request::Exit, &monitors, None, true).unwrap();
        assert!(!state.fullscreen);
        assert!(exit.decorations);
        assert_eq!(exit.restore.unwrap().frame, original());
        let enter = plan(&mut state, Request::Enter, &monitors, None, true).unwrap();
        assert!(state.fullscreen);
        assert!(!enter.decorations);
        assert!(enter.restore.is_none());
        assert_eq!(state.windowed, original());
        plan(&mut state, Request::Toggle, &monitors, None, true).unwrap();
        assert!(!state.fullscreen);
        plan(&mut state, Request::Toggle, &monitors, None, true).unwrap();
        assert!(state.fullscreen);
        let left = plan(&mut state, Request::Toggle, &monitors, None, true).unwrap();
        assert!(!state.fullscreen);
        assert_eq!(left.restore.unwrap().frame, original());
        let again = plan(&mut state, Request::Exit, &monitors, None, true).unwrap();
        assert!(again.unchanged);
        assert_eq!(state.windowed, original());
    }

    #[test]
    fn a_maximized_window_restores_maximized_and_keeps_its_normal_frame() {
        let monitors = [desktop()];
        let mut state = ScreenState {
            fullscreen: true,
            windowed: original(),
            maximized: true,
        };
        let planned = plan(&mut state, Request::Exit, &monitors, None, true).unwrap();
        let restore = planned.restore.unwrap();
        assert!(restore.maximized);
        assert_eq!(state.windowed, original());
        assert!(!state.fullscreen);
    }

    #[test]
    fn an_unchanged_request_does_not_move_the_window() {
        let monitors = [desktop()];
        let mut state = launch_state(original());
        let planned = plan(&mut state, Request::Enter, &monitors, None, true).unwrap();
        assert!(planned.unchanged);
        assert_eq!(state.windowed, original());
    }

    #[test]
    fn native_failure_falls_back_to_a_normal_window() {
        let monitors = [desktop()];
        let mut state = launch_state(original());
        let error = plan(&mut state, Request::Exit, &monitors, None, false).unwrap_err();
        assert!(error.contains("normal window"));
        assert!(!state.fullscreen);
        assert_eq!(state.windowed, original());
    }

    #[test]
    fn a_second_toggle_is_rejected_while_one_is_in_progress() {
        let controller = ScreenController::default();
        let _held = controller.try_begin().unwrap();
        let error = controller.try_begin().unwrap_err();
        assert!(error.contains("already in progress"));
    }

    #[test]
    fn previous_dimensions_restore_on_common_desktop_sizes() {
        let saved = original();
        for monitor in [
            MonitorArea { x: 0, y: 0, width: 1920, height: 1040 },
            MonitorArea { x: 0, y: 0, width: 2560, height: 1400 },
            MonitorArea { x: 0, y: 0, width: 3840, height: 2060 },
        ] {
            assert_eq!(restore_target(saved, &[monitor], Some(monitor)), saved);
        }
    }

    #[test]
    fn a_frame_larger_than_a_1366_display_is_fitted_to_the_work_area() {
        let laptop = MonitorArea {
            x: 0,
            y: 0,
            width: 1366,
            height: 728,
        };
        let restored = restore_target(original(), &[laptop], Some(laptop));
        assert!(contained(restored, laptop));
        assert!(restored.width <= 1366);
        assert!(restored.height <= 728);
    }

    #[test]
    fn a_disconnected_monitor_moves_the_window_onto_the_current_display() {
        let saved = Frame {
            x: 2000,
            y: 100,
            width: 1200,
            height: 800,
        };
        let primary = MonitorArea {
            x: 0,
            y: 0,
            width: 1920,
            height: 1080,
        };
        let restored = restore_target(saved, &[primary], Some(primary));
        assert!(contained(restored, primary));
        assert_eq!((restored.width, restored.height), (1200, 800));
        assert!(restored.x >= primary.x);
    }

    #[test]
    fn an_invalid_position_is_brought_back_onto_a_monitor() {
        let saved = Frame {
            x: -8000,
            y: -8000,
            width: 1440,
            height: 900,
        };
        let monitor = desktop();
        let restored = restore_target(saved, &[monitor], Some(monitor));
        assert!(contained(restored, monitor));
        assert_eq!((restored.width, restored.height), (1440, 900));
    }

    #[test]
    fn a_valid_position_on_a_secondary_monitor_is_kept() {
        let secondary = MonitorArea {
            x: 1920,
            y: 0,
            width: 1920,
            height: 1080,
        };
        let saved = Frame {
            x: 2100,
            y: 120,
            width: 1440,
            height: 900,
        };
        let monitors = [
            MonitorArea {
                x: 0,
                y: 0,
                width: 1920,
                height: 1080,
            },
            secondary,
        ];
        assert_eq!(restore_target(saved, &monitors, Some(secondary)), saved);
    }
}
