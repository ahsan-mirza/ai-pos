//! Product photos on disk, so the till can paint them with no connection to the server.
//! The catalog keeps the remote URL. A file is named from that URL's WebP key, and a changed photo is a new key.

use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use crate::db::ProductRow;
use crate::sync;

const MAX_BYTES: u64 = 1_500_000;

/// `.../products/{32 hex}.webp` or `.../{32 hex}-thumb.webp`, ignoring the query string.
pub fn cache_name(url: &str) -> Option<String> {
    if url.contains("..") {
        return None;
    }
    let path = url.split(['?', '#']).next()?;
    let name = path.rsplit(['/', '\\']).next()?.to_ascii_lowercase();
    let stem = name.strip_suffix(".webp")?;
    let hex = stem.strip_suffix("-thumb").unwrap_or(stem);
    if hex.len() == 32 && hex.chars().all(|char| char.is_ascii_hexdigit()) {
        Some(name)
    } else {
        None
    }
}

fn file_for(dir: &Path, url: &str) -> Option<PathBuf> {
    Some(dir.join(cache_name(url)?))
}

pub fn local_path(dir: &Path, url: &str) -> Option<PathBuf> {
    let path = file_for(dir, url)?;
    path.is_file().then_some(path)
}

pub fn urls(products: &[ProductRow]) -> Vec<String> {
    let mut urls = Vec::new();
    for product in products {
        if let Some(url) = product
            .thumb_url
            .as_deref()
            .filter(|url| cache_name(url).is_some())
        {
            urls.push(url.to_string());
        }
        if let Some(url) = product
            .image_url
            .as_deref()
            .filter(|url| cache_name(url).is_some())
        {
            urls.push(url.to_string());
        }
    }
    urls.sort();
    urls.dedup();
    urls
}

/// Download WebP files that are not already on disk. Returns whether anything new was saved.
/// A failed download is skipped; the card keeps the remote URL until the file exists.
pub fn download_missing(dir: &Path, urls: &[String]) -> bool {
    if urls.is_empty() {
        return false;
    }
    let Ok(client) = sync::client() else {
        return false;
    };
    if fs::create_dir_all(dir).is_err() {
        return false;
    }
    let mut saved = false;
    let mut wanted = Vec::new();
    for url in urls {
        let Some(name) = cache_name(url) else {
            continue;
        };
        wanted.push(name.clone());
        let path = dir.join(&name);
        if path.is_file() {
            continue;
        }
        if save(&client, url, &path) {
            saved = true;
        }
    }
    saved |= prune(dir, &wanted);
    saved
}

fn save(client: &reqwest::blocking::Client, url: &str, path: &Path) -> bool {
    let response = match client.get(url).send() {
        Ok(response) if response.status().is_success() => response,
        _ => return false,
    };
    if response
        .content_length()
        .is_some_and(|length| length > MAX_BYTES)
    {
        return false;
    }
    let mut body = Vec::new();
    if response.take(MAX_BYTES + 1).read_to_end(&mut body).is_err()
        || body.is_empty()
        || body.len() as u64 > MAX_BYTES
    {
        return false;
    }
    let partial = path.with_extension("part");
    if fs::write(&partial, &body).is_err() {
        return false;
    }
    fs::rename(&partial, path).is_ok()
}

/// Drop photos whose product no longer points at them.
fn prune(dir: &Path, wanted: &[String]) -> bool {
    let Ok(entries) = fs::read_dir(dir) else {
        return false;
    };
    let mut removed = false;
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if cache_name(&name).is_none() || wanted.iter().any(|item| item == &name) {
            continue;
        }
        if fs::remove_file(entry.path()).is_ok() {
            removed = true;
        }
    }
    removed
}

#[cfg(test)]
mod tests {
    use super::cache_name;

    #[test]
    fn names_a_product_webp_and_rejects_anything_else() {
        let full =
            "http://130.210.53.214/media/demo/products/0123456789abcdef0123456789abcdef.webp";
        let thumb = "http://130.210.53.214/media/demo/products/0123456789abcdef0123456789abcdef-thumb.webp?v=1";
        assert_eq!(
            cache_name(full).as_deref(),
            Some("0123456789abcdef0123456789abcdef.webp")
        );
        assert_eq!(
            cache_name(thumb).as_deref(),
            Some("0123456789abcdef0123456789abcdef-thumb.webp")
        );
        assert_eq!(
            cache_name("http://130.210.53.214/media/demo/products/logo.png"),
            None
        );
        assert_eq!(cache_name("../0123456789abcdef0123456789abcdef.webp"), None);
    }
}
