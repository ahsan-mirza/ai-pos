//! Windows-driver receipt printing.
//!
//! A native Windows driver, such as Toshiba Native Windows Driver on a `Toshiba:` port, renders a
//! GDI page. Raw ESC/POS sent as datatype RAW is accepted by the spooler and then discarded, so the
//! printer feeds and cuts a blank slip. This module draws the same 1-bit raster the receipt
//! renderer already produced. It does not send a drawer pulse.

use crate::printer_discovery::{self, RENDER_FAILED, TRANSMIT_FAILED};

/// Packed 1-bit rows are 203 dots per inch. 384 dots is 58 mm paper and 576 dots is 80 mm paper.
pub fn paper_size_tenths(width_dots: u32, height_dots: u32) -> (i16, i16) {
    let width = if width_dots <= 384 { 580 } else { 800 };
    // Tenths of a millimetre at 203 dpi, plus a short tail so the last line is not clipped.
    // The previous 300 mm cap kept only the top of a long slip.
    let length = ((height_dots as i64) * 254 / 203 + 150).clamp(400, 32_000);
    (width, length as i16)
}

/// Source rows for each driver page. Roll printing does not use this; a short page must not become a new form.
#[cfg_attr(not(test), allow(dead_code))]
pub fn page_slices(height: u32, rows_per_page: u32) -> Vec<(u32, u32)> {
    let page = rows_per_page.max(1);
    let mut slices = Vec::new();
    let mut start = 0;
    while start < height {
        let rows = (height - start).min(page);
        slices.push((start, rows));
        start += rows;
    }
    slices
}

#[cfg_attr(not(test), allow(dead_code))]
pub fn slice_packed(width: u32, packed: &[u8], start: u32, rows: u32) -> Result<Vec<u8>, String> {
    let row_bytes = width.div_ceil(8) as usize;
    let from = start as usize * row_bytes;
    let to = from + rows as usize * row_bytes;
    if rows == 0 || to > packed.len() {
        return Err("The receipt image is malformed.".into());
    }
    Ok(packed[from..to].to_vec())
}

/// Band size in driver pixels. A 203 dpi device gets the raster's own dots, so the driver
/// does not resample black type into gray. Any other dpi keeps the physical width.
pub fn band_destination(src_w: u32, src_h: u32, dpi: i32, printable: i32) -> (i32, i32) {
    if (150..=240).contains(&dpi) {
        return (src_w.max(1) as i32, src_h.max(1) as i32);
    }
    gdi_destination(src_w, src_h, dpi, printable)
}

/// Destination size in driver pixels. The image keeps its physical width.
/// A reported printable width far below the raster is ignored, so a 576-dot slip is not
/// squeezed into a few millimetres when the driver mixes DPI and dot counts.
pub fn gdi_destination(src_w: u32, src_h: u32, dpi: i32, printable: i32) -> (i32, i32) {
    let dpi = if dpi <= 0 { 203 } else { dpi };
    let mut dest_w = (src_w as i64 * i64::from(dpi) / 203).max(1) as i32;
    let mut dest_h = (src_h as i64 * i64::from(dpi) / 203).max(1) as i32;
    let source_mm = f64::from(src_w) / 203.0 * 25.4;
    let printable_mm = if printable > 0 {
        f64::from(printable) / f64::from(dpi) * 25.4
    } else {
        source_mm
    };
    if printable > 0 && dest_w > printable && printable_mm + 1.0 >= source_mm * 0.85 {
        dest_h = ((i64::from(dest_h) * i64::from(printable)) / i64::from(dest_w)).max(1) as i32;
        dest_w = printable;
    }
    (dest_w, dest_h)
}

/// One page for the whole raster. A short driver page used to start a new form per slice,
/// and the roll then showed the footer after a blank sheet.
pub fn roll_page(height: u32) -> Vec<(u32, u32)> {
    vec![(0, height.max(1))]
}

/// Source rows in one GDI blit. A taller bitmap can be accepted and still keep only its last rows,
/// which is the footer at the end of a blank feed. 24 rows of a 576-dot 24-bit strip stay under 64 KB.
pub const GDI_STRIP_ROWS: u32 = 24;

/// Rows flushed as their own page. A 576-dot 24-bit band of this height stays under 64 KB, so the
/// driver cannot keep only the footer. Each band is a page of its own height on a white background.
pub const GDI_BAND_ROWS: u32 = 32;

/// Page size for one flushed band, in tenths of a millimetre.
/// The length is the band's own dots at 203 dpi. Extra length is a white gap that slices the next line.
/// There is no 40 mm floor, which would turn every band into a long blank form.
pub fn band_paper_tenths(width_dots: u32, height_dots: u32) -> (i16, i16) {
    let width = if width_dots <= 384 { 580 } else { 800 };
    let length = ((height_dots.max(1) as i64) * 254 / 203).clamp(1, 32_000);
    (width, length as i16)
}

/// `(source start, source rows)` covering the raster from the top. Every band is at most `GDI_BAND_ROWS`.
pub fn gdi_bands(height: u32) -> Vec<(u32, u32)> {
    let height = height.max(1);
    let mut bands = Vec::new();
    let mut start = 0u32;
    while start < height {
        let rows = (height - start).min(GDI_BAND_ROWS);
        bands.push((start, rows));
        start += rows;
    }
    bands
}

/// 24-bit DIB bytes for one band. Callers keep a 576-dot band under 64 KB.
pub fn band_dib_bytes(width: u32, rows: u32) -> usize {
    let stride = (width as usize * 3).div_ceil(4) * 4;
    stride * rows as usize
}

/// `(source start, source rows, destination y, destination height)` covering the page without gaps.
pub fn gdi_strips(src_h: u32, dest_h: i32) -> Vec<(u32, u32, i32, i32)> {
    let src_h = src_h.max(1);
    let dest_h = dest_h.max(1);
    let mut starts = Vec::new();
    let mut start = 0u32;
    while start < src_h {
        let rows = (src_h - start).min(GDI_STRIP_ROWS);
        let y = (i64::from(start) * i64::from(dest_h) / i64::from(src_h)) as i32;
        starts.push((start, rows, y));
        start += rows;
    }
    let mut strips = Vec::with_capacity(starts.len());
    for index in 0..starts.len() {
        let next_y = starts.get(index + 1).map(|item| item.2).unwrap_or(dest_h);
        let height = (next_y - starts[index].2).max(1);
        strips.push((starts[index].0, starts[index].1, starts[index].2, height));
    }
    strips
}

/// Expands MSB-first 1-bit rows (1 = black) into a top-down 24-bit BGR DIB.
/// Production pages call `expand_rows` after the whole receipt has already been rejected if it is blank.
#[cfg_attr(not(test), allow(dead_code))]
pub fn expand_bgr24(width: u32, height: u32, packed: &[u8]) -> Result<(usize, Vec<u8>), String> {
    if !packed.iter().any(|byte| *byte != 0) {
        return Err(RENDER_FAILED.into());
    }
    expand_rows(width, height, packed)
}

/// A white slice is valid. The whole receipt is rejected before the first slice.
fn expand_rows(width: u32, height: u32, packed: &[u8]) -> Result<(usize, Vec<u8>), String> {
    let row_bytes = width.div_ceil(8) as usize;
    if width == 0 || height == 0 || packed.len() != row_bytes * height as usize {
        return Err("The receipt image is malformed.".into());
    }
    let stride = (width as usize * 3).div_ceil(4) * 4;
    let mut pixels = vec![255u8; stride * height as usize];
    for y in 0..height as usize {
        for x in 0..width as usize {
            let ink = packed[y * row_bytes + (x >> 3)] & (0x80u8 >> (x & 7));
            if ink != 0 {
                let offset = y * stride + x * 3;
                pixels[offset] = 0;
                pixels[offset + 1] = 0;
                pixels[offset + 2] = 0;
            }
        }
    }
    Ok((stride, pixels))
}

pub fn flip_bottom_up(height: u32, stride: usize, top_down: &[u8]) -> Vec<u8> {
    let mut out = vec![0u8; top_down.len()];
    let rows = height as usize;
    for y in 0..rows {
        let src = y * stride;
        let dst = (rows - 1 - y) * stride;
        out[dst..dst + stride].copy_from_slice(&top_down[src..src + stride]);
    }
    out
}

/// Windows `PASSTHROUGH` (escape 19). A RAW spooler job is discarded by some native drivers;
/// the same ESC/POS bytes inside the driver job are not.
pub const PASSTHROUGH_UNSUPPORTED: &str = "This driver does not accept raw receipt bytes inside a Windows job.";
const PASSTHROUGH_CHUNK: usize = 16 * 1024;

/// WORD length prefix plus the following bytes, in chunks a driver will accept.
pub fn passthrough_frames(bytes: &[u8]) -> Vec<Vec<u8>> {
    bytes
        .chunks(PASSTHROUGH_CHUNK)
        .filter(|chunk| !chunk.is_empty())
        .map(|chunk| {
            let mut frame = Vec::with_capacity(2 + chunk.len());
            let len = u16::try_from(chunk.len()).unwrap_or(u16::MAX);
            frame.extend_from_slice(&len.to_le_bytes());
            frame.extend_from_slice(&chunk[..len as usize]);
            frame
        })
        .collect()
}

/// True when graphic bytes appear before the feed and cut commands.
pub fn graphics_precede_cut(bytes: &[u8]) -> bool {
    let image = bytes.windows(4).position(|window| window == [0x1d, b'v', b'0', 0]);
    let cut = bytes.windows(3).position(|window| window == [0x1d, b'V', 66]);
    match (image, cut) {
        (Some(image), Some(cut)) => image < cut && bytes[image..cut].iter().any(|byte| *byte != 0),
        _ => false,
    }
}

#[cfg(windows)]
#[allow(dead_code)]
pub fn print_passthrough(name: &str, bytes: &[u8]) -> Result<i32, String> {
    use windows_sys::Win32::Foundation::GetLastError;
    use windows_sys::Win32::Graphics::Gdi::{CreateDCW, DeleteDC, PASSTHROUGH, QUERYESCSUPPORT};
    use windows_sys::Win32::Graphics::Printing::{ClosePrinter, OpenPrinterW, PRINTER_HANDLE};
    use windows_sys::Win32::Storage::Xps::{EndDoc, EndPage, ExtEscape, StartDocW, StartPage, DOCINFOW};

    if bytes.is_empty() {
        return Err(RENDER_FAILED.into());
    }
    let printer = wide(name);
    let winspool = wide("WINSPOOL");
    let document = wide("AxizPOS receipt");
    unsafe {
        let mut handle = PRINTER_HANDLE::default();
        if OpenPrinterW(printer.as_ptr(), &mut handle, std::ptr::null()) == 0 {
            return Err(format!("{} Windows error {}.", printer_discovery::QUEUE_CLOSED, GetLastError()));
        }
        // A short form. The ESC/POS bytes set the receipt length; a long driver page was the blank feed.
        let devmode = prepare_devmode(handle, printer.as_ptr(), 576, 80);
        let devmode_ptr = devmode
            .as_ref()
            .map(|mode| mode.as_ptr() as *const windows_sys::Win32::Graphics::Gdi::DEVMODEW)
            .unwrap_or(std::ptr::null());
        let hdc = CreateDCW(winspool.as_ptr(), printer.as_ptr(), std::ptr::null(), devmode_ptr);
        ClosePrinter(handle);
        if hdc.is_null() {
            return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
        }
        let drawn = (|| {
            let query = PASSTHROUGH as i32;
            if ExtEscape(hdc, QUERYESCSUPPORT as i32, 4, (&query as *const i32).cast(), 0, std::ptr::null_mut()) <= 0 {
                return Err(PASSTHROUGH_UNSUPPORTED.into());
            }
            let info = DOCINFOW {
                cbSize: std::mem::size_of::<DOCINFOW>() as i32,
                lpszDocName: document.as_ptr(),
                lpszOutput: std::ptr::null(),
                lpszDatatype: std::ptr::null(),
                fwType: 0,
            };
            let job = StartDocW(hdc, &info);
            if job <= 0 {
                return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
            }
            if StartPage(hdc) <= 0 {
                let _ = EndDoc(hdc);
                return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
            }
            for (index, frame) in passthrough_frames(bytes).into_iter().enumerate() {
                let wrote = ExtEscape(
                    hdc,
                    PASSTHROUGH as i32,
                    frame.len() as i32,
                    frame.as_ptr().cast(),
                    0,
                    std::ptr::null_mut(),
                );
                if wrote <= 0 {
                    let _ = EndPage(hdc);
                    let _ = EndDoc(hdc);
                    if index == 0 {
                        return Err(PASSTHROUGH_UNSUPPORTED.into());
                    }
                    return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
                }
            }
            if EndPage(hdc) <= 0 || EndDoc(hdc) <= 0 {
                return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
            }
            Ok(job)
        })();
        DeleteDC(hdc);
        drawn
    }
}

#[cfg(not(windows))]
pub fn print_passthrough(_name: &str, _bytes: &[u8]) -> Result<i32, String> {
    Err("Windows driver printing is only available on Windows.".into())
}

#[cfg(windows)]
fn set_band_paper(bytes: &mut [u8], width: u32, height: u32) {
    use windows_sys::Win32::Graphics::Gdi::{
        DEVMODEW, DM_ORIENTATION, DM_PAPERLENGTH, DM_PAPERSIZE, DM_PAPERWIDTH, DM_PRINTQUALITY, DM_SCALE,
        DM_YRESOLUTION, DMPAPER_USER,
    };
    if bytes.len() < std::mem::size_of::<DEVMODEW>() {
        return;
    }
    unsafe {
        let mode = bytes.as_mut_ptr().cast::<DEVMODEW>();
        let (paper_w, paper_h) = band_paper_tenths(width, height);
        (*mode).dmFields |=
            DM_ORIENTATION | DM_PAPERSIZE | DM_PAPERLENGTH | DM_PAPERWIDTH | DM_SCALE | DM_PRINTQUALITY | DM_YRESOLUTION;
        (*mode).Anonymous1.Anonymous1.dmOrientation = 1;
        (*mode).Anonymous1.Anonymous1.dmPaperSize = DMPAPER_USER as i16;
        (*mode).Anonymous1.Anonymous1.dmPaperLength = paper_h;
        (*mode).Anonymous1.Anonymous1.dmPaperWidth = paper_w;
        (*mode).Anonymous1.Anonymous1.dmScale = 100;
        (*mode).Anonymous1.Anonymous1.dmPrintQuality = 203;
        (*mode).dmYResolution = 203;
    }
}

#[cfg(windows)]
pub fn print_gdi(name: &str, width: u32, height: u32, packed: &[u8], copies: u32) -> Result<(), String> {
    use windows_sys::Win32::Foundation::GetLastError;
    use windows_sys::Win32::Graphics::Gdi::{
        CreateDCW, DeleteDC, GetDeviceCaps, SetStretchBltMode, SetViewportOrgEx, SetWindowOrgEx, COLORONCOLOR, HORZRES,
        LOGPIXELSX, PHYSICALOFFSETX, PHYSICALOFFSETY,
    };
    use windows_sys::Win32::Graphics::Printing::{ClosePrinter, OpenPrinterW, PRINTER_HANDLE};
    use windows_sys::Win32::Storage::Xps::{EndDoc, EndPage, StartDocW, StartPage, DOCINFOW};

    if !packed.iter().any(|byte| *byte != 0) {
        return Err(RENDER_FAILED.into());
    }
    let printer = wide(name);
    let winspool = wide("WINSPOOL");
    let document = wide("AxizPOS receipt");
    let bands = gdi_bands(height);
    unsafe {
        let mut handle = PRINTER_HANDLE::default();
        if OpenPrinterW(printer.as_ptr(), &mut handle, std::ptr::null()) == 0 {
            return Err(format!("{} Windows error {}.", printer_discovery::QUEUE_CLOSED, GetLastError()));
        }
        // The driver's merged page is at least 40 mm. Override it or every band is a blank form.
        let mut devmode = prepare_devmode(handle, printer.as_ptr(), width, GDI_BAND_ROWS);
        if let Some(bytes) = devmode.as_mut() {
            set_band_paper(bytes, width, GDI_BAND_ROWS);
        }
        let devmode_ptr = devmode
            .as_ref()
            .map(|bytes| bytes.as_ptr() as *const windows_sys::Win32::Graphics::Gdi::DEVMODEW)
            .unwrap_or(std::ptr::null());
        let hdc = CreateDCW(winspool.as_ptr(), printer.as_ptr(), std::ptr::null(), devmode_ptr);
        ClosePrinter(handle);
        if hdc.is_null() {
            return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
        }
        let drawn = (|| {
            let info = DOCINFOW {
                cbSize: std::mem::size_of::<DOCINFOW>() as i32,
                lpszDocName: document.as_ptr(),
                lpszOutput: std::ptr::null(),
                lpszDatatype: std::ptr::null(),
                fwType: 0,
            };
            if StartDocW(hdc, &info) <= 0 {
                return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
            }
            SetStretchBltMode(hdc, COLORONCOLOR);
            let dpi = GetDeviceCaps(hdc, LOGPIXELSX as i32);
            let printable = GetDeviceCaps(hdc, HORZRES as i32);
            let origin_x = GetDeviceCaps(hdc, PHYSICALOFFSETX as i32);
            let origin_y = GetDeviceCaps(hdc, PHYSICALOFFSETY as i32);
            let (stride, pixels) = match expand_rows(width, height, packed) {
                Ok(expanded) => expanded,
                Err(message) => {
                    let _ = EndDoc(hdc);
                    return Err(message);
                }
            };
            for _ in 0..copies.max(1) {
                for (start, rows) in &bands {
                    if StartPage(hdc) <= 0 {
                        let _ = EndDoc(hdc);
                        return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
                    }
                    // The driver's margin would otherwise start each band below the physical edge and clip its tail.
                    let _ = SetViewportOrgEx(hdc, -origin_x, -origin_y, std::ptr::null_mut());
                    let _ = SetWindowOrgEx(hdc, 0, 0, std::ptr::null_mut());
                    let from = *start as usize * stride;
                    let to = from + *rows as usize * stride;
                    let bottom_up = flip_bottom_up(*rows, stride, &pixels[from..to]);
                    let (dest_w, dest_h) = band_destination(width, *rows, dpi, printable);
                    // One blit at the top of this page, at the raster's own dots. Stretching a 1-bit
                    // slip into gray is what breaks the strokes. Several blits on one page left only the last one.
                    let painted = paint(hdc, width, *rows, stride, &bottom_up, 0, 0, dest_w, dest_h, false);
                    if EndPage(hdc) <= 0 || !painted {
                        let _ = EndDoc(hdc);
                        return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
                    }
                }
            }
            if EndDoc(hdc) <= 0 {
                return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
            }
            Ok(())
        })();
        DeleteDC(hdc);
        drawn
    }
}

#[cfg(windows)]
fn paint(
    hdc: windows_sys::Win32::Graphics::Gdi::HDC,
    width: u32,
    height: u32,
    stride: usize,
    pixels: &[u8],
    dest_x: i32,
    dest_y: i32,
    dest_w: i32,
    dest_h: i32,
    top_down: bool,
) -> bool {
    use windows_sys::Win32::Graphics::Gdi::{
        SetDIBitsToDevice, StretchDIBits, BITMAPINFO, BITMAPINFOHEADER, DIB_RGB_COLORS, SRCCOPY,
    };
    let header = BITMAPINFOHEADER {
        biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
        biWidth: width as i32,
        biHeight: if top_down { -(height as i32) } else { height as i32 },
        biPlanes: 1,
        biBitCount: 24,
        biCompression: 0,
        biSizeImage: (stride * height as usize) as u32,
        biXPelsPerMeter: 0,
        biYPelsPerMeter: 0,
        biClrUsed: 0,
        biClrImportant: 0,
    };
    let info = BITMAPINFO {
        bmiHeader: header,
        bmiColors: [windows_sys::Win32::Graphics::Gdi::RGBQUAD::default()],
    };
    let same_dots = dest_w == width as i32 && dest_h == height as i32;
    let drawn = unsafe {
        if same_dots {
            SetDIBitsToDevice(
                hdc,
                dest_x,
                dest_y,
                width,
                height,
                0,
                0,
                0,
                height,
                pixels.as_ptr().cast(),
                &info,
                DIB_RGB_COLORS,
            )
        } else {
            StretchDIBits(
                hdc,
                dest_x,
                dest_y,
                dest_w,
                dest_h,
                0,
                0,
                width as i32,
                height as i32,
                pixels.as_ptr().cast(),
                &info,
                DIB_RGB_COLORS,
                SRCCOPY,
            )
        }
    };
    drawn > 0
}

#[cfg(windows)]
fn prepare_devmode(
    handle: windows_sys::Win32::Graphics::Printing::PRINTER_HANDLE,
    name: *const u16,
    width: u32,
    height: u32,
) -> Option<Vec<u8>> {
    use windows_sys::Win32::Graphics::Gdi::{
        DEVMODEW, DM_ORIENTATION, DM_PAPERLENGTH, DM_PAPERSIZE, DM_PAPERWIDTH, DM_PRINTQUALITY, DM_SCALE,
        DM_YRESOLUTION, DMPAPER_USER,
    };
    use windows_sys::Win32::Graphics::Printing::DocumentPropertiesW;
    unsafe {
        let needed = DocumentPropertiesW(std::ptr::null_mut(), handle, name, std::ptr::null_mut(), std::ptr::null(), 0);
        if needed <= 0 {
            return None;
        }
        let mut current = vec![0u8; needed as usize];
        if DocumentPropertiesW(
            std::ptr::null_mut(),
            handle,
            name,
            current.as_mut_ptr().cast(),
            std::ptr::null(),
            2,
        ) < 0
        {
            return None;
        }
        let apply = |mode: *mut DEVMODEW| {
            let (paper_w, paper_h) = paper_size_tenths(width, height);
            (*mode).dmFields |=
                DM_ORIENTATION | DM_PAPERSIZE | DM_PAPERLENGTH | DM_PAPERWIDTH | DM_SCALE | DM_PRINTQUALITY | DM_YRESOLUTION;
            (*mode).Anonymous1.Anonymous1.dmOrientation = 1;
            (*mode).Anonymous1.Anonymous1.dmPaperSize = DMPAPER_USER as i16;
            (*mode).Anonymous1.Anonymous1.dmPaperLength = paper_h;
            (*mode).Anonymous1.Anonymous1.dmPaperWidth = paper_w;
            (*mode).Anonymous1.Anonymous1.dmScale = 100;
            (*mode).Anonymous1.Anonymous1.dmPrintQuality = 203;
            (*mode).dmYResolution = 203;
        };
        apply(current.as_mut_ptr().cast());
        let mut updated = current.clone();
        if DocumentPropertiesW(
            std::ptr::null_mut(),
            handle,
            name,
            updated.as_mut_ptr().cast(),
            current.as_ptr().cast(),
            10,
        ) < 0
        {
            return Some(current);
        }
        // The driver merge can restore a long default page. Put the raster's page size back.
        apply(updated.as_mut_ptr().cast());
        Some(updated)
    }
}

#[cfg(windows)]
fn wide(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(std::iter::once(0)).collect()
}

#[cfg(windows)]
pub fn print_gdi_text(name: &str, text: &str, copies: u32) -> Result<(), String> {
    use windows_sys::Win32::Foundation::GetLastError;
    use windows_sys::Win32::Graphics::Gdi::{
        CreateDCW, CreateFontW, DeleteDC, DeleteObject, GetDeviceCaps, GetTextMetricsW, SelectObject, SetBkMode,
        SetTextColor, TextOutW, CLIP_DEFAULT_PRECIS, DEFAULT_CHARSET, DEFAULT_PITCH, DEFAULT_QUALITY, FW_NORMAL,
        HORZRES, LOGPIXELSY, OUT_DEFAULT_PRECIS, TEXTMETRICW, TRANSPARENT, VERTRES,
    };
    use windows_sys::Win32::Graphics::Printing::{ClosePrinter, OpenPrinterW, PRINTER_HANDLE};
    use windows_sys::Win32::Storage::Xps::{EndDoc, EndPage, StartDocW, StartPage, DOCINFOW};

    let lines: Vec<&str> = text.split('\n').map(|line| line.trim_end_matches('\r')).collect();
    if lines.iter().all(|line| line.trim().is_empty()) {
        return Err(printer_discovery::RENDER_FAILED.into());
    }
    let printer = wide(name);
    let winspool = wide("WINSPOOL");
    let document = wide("AxizPOS receipt");
    let face = wide("Courier New");
    unsafe {
        let mut handle = PRINTER_HANDLE::default();
        if OpenPrinterW(printer.as_ptr(), &mut handle, std::ptr::null()) == 0 {
            return Err(format!("{} Windows error {}.", printer_discovery::QUEUE_CLOSED, GetLastError()));
        }
        let height_dots = (lines.len() as u32).saturating_mul(28).max(400);
        let devmode = prepare_devmode(handle, printer.as_ptr(), 576, height_dots);
        let devmode_ptr = devmode
            .as_ref()
            .map(|bytes| bytes.as_ptr() as *const windows_sys::Win32::Graphics::Gdi::DEVMODEW)
            .unwrap_or(std::ptr::null());
        let mut hdc = CreateDCW(winspool.as_ptr(), printer.as_ptr(), std::ptr::null(), devmode_ptr);
        if hdc.is_null() {
            hdc = CreateDCW(winspool.as_ptr(), printer.as_ptr(), std::ptr::null(), std::ptr::null());
        }
        ClosePrinter(handle);
        if hdc.is_null() {
            return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
        }
        let drawn = (|| {
            let info = DOCINFOW {
                cbSize: std::mem::size_of::<DOCINFOW>() as i32,
                lpszDocName: document.as_ptr(),
                lpszOutput: std::ptr::null(),
                lpszDatatype: std::ptr::null(),
                fwType: 0,
            };
            if StartDocW(hdc, &info) <= 0 {
                return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
            }
            let dpi = GetDeviceCaps(hdc, LOGPIXELSY as i32).max(96);
            let font = CreateFontW(
                -(dpi * 10 / 72).max(12),
                0,
                0,
                0,
                FW_NORMAL as i32,
                0,
                0,
                0,
                DEFAULT_CHARSET as u32,
                OUT_DEFAULT_PRECIS as u32,
                CLIP_DEFAULT_PRECIS as u32,
                DEFAULT_QUALITY as u32,
                DEFAULT_PITCH as u32,
                face.as_ptr(),
            );
            if font.is_null() {
                let _ = EndDoc(hdc);
                return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
            }
            let previous = SelectObject(hdc, font);
            SetBkMode(hdc, TRANSPARENT as i32);
            SetTextColor(hdc, 0);
            let mut metrics = TEXTMETRICW::default();
            if GetTextMetricsW(hdc, &mut metrics) == 0 {
                SelectObject(hdc, previous);
                let _ = DeleteObject(font);
                let _ = EndDoc(hdc);
                return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
            }
            let line_h = (metrics.tmHeight + metrics.tmExternalLeading).max(12);
            let page_h = GetDeviceCaps(hdc, VERTRES as i32).max(line_h + 40);
            let margin = (GetDeviceCaps(hdc, HORZRES as i32) / 20).clamp(8, 48);
            for _ in 0..copies.max(1) {
                if StartPage(hdc) <= 0 {
                    SelectObject(hdc, previous);
                    let _ = DeleteObject(font);
                    let _ = EndDoc(hdc);
                    return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
                }
                let mut y = margin;
                for line in &lines {
                    if y + line_h > page_h - margin {
                        if EndPage(hdc) <= 0 || StartPage(hdc) <= 0 {
                            SelectObject(hdc, previous);
                            let _ = DeleteObject(font);
                            let _ = EndDoc(hdc);
                            return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
                        }
                        y = margin;
                    }
                    let wide_line = wide(line);
                    let count = wide_line.len().saturating_sub(1) as i32;
                    if count > 0 && TextOutW(hdc, margin, y, wide_line.as_ptr(), count) == 0 {
                        let _ = EndPage(hdc);
                        SelectObject(hdc, previous);
                        let _ = DeleteObject(font);
                        let _ = EndDoc(hdc);
                        return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
                    }
                    y += line_h;
                }
                if EndPage(hdc) <= 0 {
                    SelectObject(hdc, previous);
                    let _ = DeleteObject(font);
                    let _ = EndDoc(hdc);
                    return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
                }
            }
            SelectObject(hdc, previous);
            let _ = DeleteObject(font);
            if EndDoc(hdc) <= 0 {
                return Err(format!("{TRANSMIT_FAILED} Windows error {}.", GetLastError()));
            }
            Ok(())
        })();
        DeleteDC(hdc);
        drawn
    }
}

#[cfg(not(windows))]
pub fn print_gdi(_name: &str, _width: u32, _height: u32, _packed: &[u8], _copies: u32) -> Result<(), String> {
    Err("Windows driver printing is only available on Windows.".into())
}

#[cfg(not(windows))]
pub fn print_gdi_text(_name: &str, _text: &str, _copies: u32) -> Result<(), String> {
    Err("Windows driver printing is only available on Windows.".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn paper_width_follows_the_raster_and_not_a_fixed_page() {
        assert_eq!(paper_size_tenths(384, 400).0, 580);
        assert_eq!(paper_size_tenths(576, 800).0, 800);
        assert!(paper_size_tenths(576, 800).1 > paper_size_tenths(576, 200).1);
        assert!(paper_size_tenths(576, 4_000).1 > 3_000);
        let slices = page_slices(1_000, 250);
        assert_eq!(slices, vec![(0, 250), (250, 250), (500, 250), (750, 250)]);
        assert_eq!(page_slices(1_000, 1_000), vec![(0, 1_000)]);
        let packed = vec![0xffu8; 8];
        assert_eq!(slice_packed(16, &packed, 1, 1).unwrap(), vec![0xff, 0xff]);
    }

    #[test]
    fn destination_keeps_58_mm_narrower_than_80_mm() {
        let narrow = gdi_destination(384, 600, 203, 576);
        let wide = gdi_destination(576, 600, 203, 576);
        assert!(narrow.0 < wide.0);
        assert_eq!(wide.0, 576);
        let scaled = gdi_destination(576, 600, 300, 400);
        let kept = (576i64 * 300 / 203) as i32;
        assert_eq!(scaled.0, kept);
        assert!(scaled.1 > 600);
        assert_eq!(roll_page(1_000), vec![(0, 1_000)]);
    }

    #[test]
    fn a_tall_receipt_is_drawn_in_short_strips_from_the_top() {
        let strips = gdi_strips(1_000, 1_000);
        assert!(strips.len() > 1);
        assert!(strips.iter().all(|strip| strip.1 <= GDI_STRIP_ROWS));
        assert_eq!(strips[0].0, 0);
        assert_eq!(strips[0].2, 0);
        let mut covered = 0i32;
        for window in strips.windows(2) {
            assert_eq!(window[0].2 + window[0].3, window[1].2);
            covered = window[1].2 + window[1].3;
        }
        assert_eq!(covered, 1_000);
        let wide = gdi_strips(48, 96);
        assert_eq!(wide[0], (0, 24, 0, 48));
        assert_eq!(wide[1], (24, 24, 48, 48));
        let stride = (576usize * 3).div_ceil(4) * 4;
        assert!(stride * GDI_STRIP_ROWS as usize <= 65_536);
    }

    #[test]
    fn each_band_is_a_short_page_from_the_top() {
        let bands = gdi_bands(1_000);
        assert!(bands.len() > 1);
        assert_eq!(bands[0], (0, GDI_BAND_ROWS));
        assert_eq!(bands.iter().map(|band| band.1).sum::<u32>(), 1_000);
        assert!(bands.iter().all(|band| band.1 <= GDI_BAND_ROWS && band.1 > 0));
        let mut cursor = 0u32;
        for (start, rows) in &bands {
            assert_eq!(*start, cursor);
            cursor += rows;
        }
        let (_width, length) = band_paper_tenths(576, GDI_BAND_ROWS);
        assert_eq!(length, 40);
        assert!(length < 400);
        assert_eq!(band_destination(576, 32, 203, 576), (576, 32));
        assert_eq!(band_destination(576, 32, 180, 400).0, 576);
        assert!(band_dib_bytes(576, GDI_BAND_ROWS) <= 65_536);
        assert!(band_dib_bytes(384, GDI_BAND_ROWS) < band_dib_bytes(576, GDI_BAND_ROWS));
    }

    #[test]
    fn black_bits_become_black_pixels_and_a_blank_raster_is_rejected() {
        let (stride, pixels) = expand_bgr24(8, 1, &[0b1000_0000]).unwrap();
        assert_eq!(stride, 24);
        assert_eq!(&pixels[0..3], &[0, 0, 0]);
        assert_eq!(&pixels[3..6], &[255, 255, 255]);
        assert!(expand_bgr24(8, 1, &[0]).unwrap_err().contains("could not be rendered"));
    }

    #[test]
    fn passthrough_frames_keep_the_escpos_bytes_in_order() {
        let payload: Vec<u8> = (0..20_000).map(|index| (index % 251) as u8).collect();
        let frames = passthrough_frames(&payload);
        assert!(frames.len() >= 2);
        let mut restored = Vec::new();
        for frame in &frames {
            assert!(frame.len() > 2);
            assert!(frame.len() <= 2 + 16 * 1024);
            let len = u16::from_le_bytes([frame[0], frame[1]]) as usize;
            assert_eq!(len, frame.len() - 2);
            restored.extend_from_slice(&frame[2..]);
        }
        assert_eq!(restored, payload);
        assert!(passthrough_frames(&[]).is_empty());
    }

    #[test]
    fn escpos_graphics_come_before_the_cut() {
        let mut bytes = vec![0x1b, b'@', 0x1d, b'v', b'0', 0, 0xff];
        bytes.extend_from_slice(&[0x1b, b'd', 4, 0x1d, b'V', 66, 0]);
        assert!(graphics_precede_cut(&bytes));
        let cut_only = [0x1d, b'V', 66, 0];
        assert!(!graphics_precede_cut(&cut_only));
    }
}
