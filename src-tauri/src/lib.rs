//! Native services with tests that can run without a display or WebView.
pub mod backend;
pub mod desktop_files;
pub mod export;
#[cfg(feature = "native-notifications")]
pub mod notifications;
mod process;
