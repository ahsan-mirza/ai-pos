//! Server reachability. This module does not open a socket.

pub const OFFLINE_NOTICE: &str = "You're working offline. Local POS operations remain available. Pending changes will synchronize when a connection is restored.";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EndpointKind {
    Unactivated,
    Https,
    Development,
    Insecure,
    Invalid,
}

pub fn endpoint_kind(url: &str, release: bool) -> EndpointKind {
    let value = url.trim();
    if value.is_empty() || value.contains("not-activated") {
        return EndpointKind::Unactivated;
    }
    let Some(rest) = value.split_once("://") else {
        return EndpointKind::Invalid;
    };
    let (scheme, after) = rest;
    let host = after.split(['/', ':', '?', '#']).next().unwrap_or("");
    let loopback = host.eq_ignore_ascii_case("localhost") || host == "127.0.0.1" || host == "[::1]" || host == "::1";
    if scheme == "https" {
        return EndpointKind::Https;
    }
    if scheme == "http" && loopback && !release {
        return EndpointKind::Development;
    }
    if scheme == "http" {
        return EndpointKind::Insecure;
    }
    EndpointKind::Invalid
}

pub fn may_probe(kind: EndpointKind) -> bool {
    matches!(kind, EndpointKind::Https | EndpointKind::Development)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LinkState {
    Online,
    Offline,
    Reconnecting,
    NotActivated,
}

pub fn link_state(activated: bool, reachable: bool, syncing: bool) -> LinkState {
    if !activated {
        return LinkState::NotActivated;
    }
    if syncing && !reachable {
        return LinkState::Reconnecting;
    }
    if reachable {
        LinkState::Online
    } else {
        LinkState::Offline
    }
}

pub fn link_message(state: LinkState, kind: EndpointKind) -> &'static str {
    if state == LinkState::NotActivated {
        return "This register is not activated. Local setup can continue. No remote server is assumed.";
    }
    if kind == EndpointKind::Insecure {
        return "The configured server is not HTTPS, so AxizPOS will not send the register's data to it. Local POS operations remain available.";
    }
    if kind == EndpointKind::Invalid {
        return "The configured server address is not a valid URL. Local POS operations remain available.";
    }
    match state {
        LinkState::Online => "The register can reach its configured server. A submitted change is synchronized only after the server accepts it.",
        LinkState::Reconnecting => "Reconnecting. Local POS operations remain available. Pending changes stay queued until the server accepts them.",
        LinkState::Offline | LinkState::NotActivated => OFFLINE_NOTICE,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn localhost_is_a_development_url_and_a_remote_http_url_is_not_called() {
        assert_eq!(endpoint_kind("http://localhost:8000", false), EndpointKind::Development);
        assert_eq!(endpoint_kind("http://localhost:8000", true), EndpointKind::Insecure);
        assert_eq!(endpoint_kind("https://client1.example.com", true), EndpointKind::Https);
        assert_eq!(endpoint_kind("http://client1.example.com", false), EndpointKind::Insecure);
        assert_eq!(endpoint_kind("http://not-activated.invalid", false), EndpointKind::Unactivated);
        assert!(may_probe(EndpointKind::Development));
        assert!(may_probe(EndpointKind::Https));
        assert!(!may_probe(EndpointKind::Insecure));
        assert_eq!(link_state(true, false, true), LinkState::Reconnecting);
        assert_eq!(link_state(true, false, false), LinkState::Offline);
        assert_eq!(link_state(false, false, false), LinkState::NotActivated);
        assert!(link_message(LinkState::Offline, EndpointKind::Https).contains("working offline"));
        assert!(!link_message(LinkState::Offline, EndpointKind::Development).contains("localhost:8000"));
    }
}
