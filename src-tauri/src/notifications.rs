#[cfg(windows)]
pub fn show(identifier: &str, title: &str, message: &str, sound: bool) -> Result<(), String> {
    use windows::{
        core::HSTRING,
        Data::Xml::Dom::XmlDocument,
        UI::Notifications::{NotificationSetting, ToastNotification, ToastNotificationManager},
    };
    let fail = |_| {
        "Windows no ha aceptado el aviso. Revisa Configuración de Windows → Sistema → Notificaciones. Los avisos siguen disponibles en la aplicación.".to_owned()
    };
    let notifier = ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(identifier))
        .map_err(fail)?;
    if notifier.Setting().map_err(fail)? != NotificationSetting::Enabled {
        return Err("Windows tiene desactivadas estas notificaciones. Actívalas en Configuración de Windows → Sistema → Notificaciones. Los avisos siguen dentro de la aplicación.".into());
    }
    let document = XmlDocument::new().map_err(fail)?;
    let escape = |text: &str| {
        text.replace('&', "&amp;")
            .replace('<', "&lt;")
            .replace('>', "&gt;")
            .replace('"', "&quot;")
            .replace('\'', "&apos;")
    };
    let audio = if sound {
        "<audio src=\"ms-winsoundevent:Notification.Default\"/>"
    } else {
        "<audio silent=\"true\"/>"
    };
    document.LoadXml(&HSTRING::from(format!("<toast><visual><binding template=\"ToastGeneric\"><text>{}</text><text>{}</text></binding></visual>{audio}</toast>", escape(title), escape(message)))).map_err(fail)?;
    let toast = ToastNotification::CreateToastNotification(&document).map_err(fail)?;
    toast.SetTag(&HSTRING::from("agenda")).map_err(fail)?;
    toast.SetGroup(&HSTRING::from("canamo")).map_err(fail)?;
    notifier.Show(&toast).map_err(fail)
}

#[cfg(not(windows))]
pub fn show(_identifier: &str, title: &str, message: &str, sound: bool) -> Result<(), String> {
    let mut notification = notify_rust::Notification::new();
    notification
        .summary(title)
        .body(message)
        .appname("Talleres El Cáñamo");
    #[cfg(target_os = "linux")]
    notification.hint(notify_rust::Hint::SuppressSound(!sound));
    notification.show().map(|_| ()).map_err(|_| "El sistema no ha aceptado el aviso. Los recordatorios siguen disponibles dentro de la aplicación.".to_owned())
}
