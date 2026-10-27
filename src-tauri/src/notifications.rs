use serde_json::{json, Value};
use std::{
    collections::{HashMap, HashSet},
    sync::Arc,
};

pub const DELIVERY_ERROR: &str = "No se ha podido confirmar el aviso. Los recordatorios siguen dentro de la aplicación y se reintentará sin repetir el sonido.";

/// OS acceptance survives an acknowledgement failure within this process.
/// A snooze changes due_at and therefore creates a new delivery.
#[derive(Default)]
pub struct DeliveryLedger {
    accepted: HashMap<(String, String), Value>,
}

fn delivery_key(item: &Value) -> Result<(String, String), String> {
    match (item["id"].as_str(), item["due_at"].as_str()) {
        (Some(id), Some(due)) if !id.is_empty() && !due.is_empty() => Ok((id.into(), due.into())),
        _ => Err("No se ha podido leer el recordatorio. Abre la agenda para revisarlo.".into()),
    }
}

impl DeliveryLedger {
    pub fn unseen(&mut self, items: &[Value]) -> Result<Vec<Value>, String> {
        let keys = items
            .iter()
            .map(delivery_key)
            .collect::<Result<HashSet<_>, _>>()?;
        self.accepted.retain(|key, _| keys.contains(key));
        let mut unseen = Vec::new();
        for item in items {
            if !self.accepted.contains_key(&delivery_key(item)?) {
                unseen.push(item.clone());
            }
        }
        Ok(unseen)
    }

    pub fn remember_accepted(&mut self, items: &[Value]) -> Result<(), String> {
        for item in items {
            self.accepted
                .entry(delivery_key(item)?)
                .or_insert_with(|| item.clone());
        }
        Ok(())
    }

    pub fn accepted_for(&self, items: &[Value]) -> Result<Vec<Value>, String> {
        items
            .iter()
            .map(|item| {
                self.accepted
                    .get(&delivery_key(item)?)
                    .cloned()
                    .ok_or_else(|| DELIVERY_ERROR.to_owned())
            })
            .collect()
    }
}

pub fn check_acknowledgement(reply: &Value) -> Result<(), String> {
    if reply["ok"] == true && reply["result"]["updated"].is_u64() {
        Ok(())
    } else {
        Err(DELIVERY_ERROR.into())
    }
}

/// Opening the agenda is safe for grouped or rescheduled occurrences too.
pub fn agenda_target() -> Value {
    json!({"destination": "agenda"})
}

fn xml_escape(text: &str) -> String {
    text.chars()
        .map(|ch| match ch {
            '&' => "&amp;".to_owned(),
            '<' => "&lt;".to_owned(),
            '>' => "&gt;".to_owned(),
            '"' => "&quot;".to_owned(),
            '\'' => "&apos;".to_owned(),
            '\t' | '\n' | '\r' => ch.to_string(),
            ch if ch < '\u{20}' || ch == '\u{fffe}' || ch == '\u{ffff}' => "�".to_owned(),
            _ => ch.to_string(),
        })
        .collect()
}

pub fn toast_xml(title: &str, message: &str, sound: bool) -> String {
    let audio = if sound {
        "<audio src=\"ms-winsoundevent:Notification.Default\" loop=\"false\"/>"
    } else {
        "<audio silent=\"true\"/>"
    };
    format!("<toast launch=\"{}\"><visual><binding template=\"ToastGeneric\"><text>{}</text><text>{}</text></binding></visual>{audio}</toast>",
        xml_escape(&agenda_target().to_string()), xml_escape(title), xml_escape(message))
}

/// Retain the Windows event source and revoke its handler when replaced.
pub struct ActiveNotification {
    #[cfg(windows)]
    toast: windows::UI::Notifications::ToastNotification,
    #[cfg(windows)]
    activation_token: i64,
}

#[cfg(windows)]
impl Drop for ActiveNotification {
    fn drop(&mut self) {
        let _ = self.toast.RemoveActivated(self.activation_token);
    }
}

#[cfg(windows)]
pub fn show(
    identifier: &str,
    title: &str,
    message: &str,
    sound: bool,
    tag: &str,
    activate: Arc<dyn Fn() + Send + Sync>,
) -> Result<ActiveNotification, String> {
    use windows::{
        core::HSTRING,
        Data::Xml::Dom::XmlDocument,
        Foundation::TypedEventHandler,
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
    document
        .LoadXml(&HSTRING::from(toast_xml(title, message, sound)))
        .map_err(fail)?;
    let toast = ToastNotification::CreateToastNotification(&document).map_err(fail)?;
    toast.SetTag(&HSTRING::from(tag)).map_err(fail)?;
    toast.SetGroup(&HSTRING::from("canamo")).map_err(fail)?;
    let activation_token = toast
        .Activated(&TypedEventHandler::new(move |_, _| {
            activate();
            Ok(())
        }))
        .map_err(fail)?;
    let active = ActiveNotification {
        toast,
        activation_token,
    };
    notifier.Show(&active.toast).map_err(fail)?;
    Ok(active)
}

#[cfg(not(windows))]
pub fn show(
    _identifier: &str,
    title: &str,
    message: &str,
    sound: bool,
    _tag: &str,
    _activate: Arc<dyn Fn() + Send + Sync>,
) -> Result<ActiveNotification, String> {
    let mut notification = notify_rust::Notification::new();
    notification
        .summary(title)
        .body(message)
        .appname("Talleres El Cáñamo");
    #[cfg(target_os = "linux")]
    notification.hint(notify_rust::Hint::SuppressSound(!sound));
    notification.show().map(|_| ActiveNotification {}).map_err(|_| "El sistema no ha aceptado el aviso. Los recordatorios siguen disponibles dentro de la aplicación.".to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn reminder(id: &str, due: &str) -> Value {
        json!({"id": id, "due_at": due})
    }

    #[test]
    fn xml_preserves_unicode_and_escapes_text_and_action_payload() {
        let xml = toast_xml(
            "Taller & <prueba>",
            "Cita \"sintética\" 'mañana'\u{0}\n",
            true,
        );
        assert!(xml.contains("Taller &amp; &lt;prueba&gt;"));
        assert!(xml.contains("Cita &quot;sintética&quot; &apos;mañana&apos;�\n"));
        assert!(xml.contains("launch=\"{&quot;destination&quot;:&quot;agenda&quot;}\""));
        assert!(!xml.contains('\0'));
        assert!(!xml.contains("<prueba>"));
        assert_eq!(agenda_target(), json!({"destination":"agenda"}));
    }

    #[test]
    fn sound_is_normal_system_audio_once_and_silent_requests_no_audio() {
        let audible = toast_xml("Prueba", "Aviso", true);
        assert!(audible.contains("ms-winsoundevent:Notification.Default\" loop=\"false\""));
        assert!(!audible.contains("scenario="));
        let silent = toast_xml("Prueba", "Aviso", false);
        assert!(silent.contains("<audio silent=\"true\"/>"));
        assert!(!silent.contains("ms-winsoundevent"));
        assert!(!silent.contains("loop=\"true\""));
    }

    #[test]
    fn failed_ack_retries_without_repeating_accepted_notification() {
        let mut ledger = DeliveryLedger::default();
        let pending = vec![reminder("one", "first")];
        assert_eq!(ledger.unseen(&pending).unwrap(), pending);
        ledger.remember_accepted(&pending).unwrap();
        assert!(
            check_acknowledgement(&json!({"ok":false,"error":{"message":"synthetic"}})).is_err()
        );
        assert!(ledger.unseen(&pending).unwrap().is_empty());
        assert!(check_acknowledgement(&json!({"ok":true,"result":{"updated":0}})).is_ok());
        assert!(check_acknowledgement(&json!({"ok":true})).is_err());
        assert_eq!(
            ledger.unseen(&[reminder("one", "snoozed")]).unwrap().len(),
            1
        );
        ledger.unseen(&[]).unwrap();
        assert!(ledger.accepted.is_empty());
    }

    #[test]
    fn retry_ack_uses_accepted_members_not_a_concurrent_group_refresh() {
        let mut ledger = DeliveryLedger::default();
        let original = json!({"id":"one", "due_at":"due", "delivery_members":[
            {"id":"one", "due_at":"due"}
        ]});
        ledger.remember_accepted(&[original.clone()]).unwrap();
        let refreshed = json!({"id":"one", "due_at":"due", "delivery_members":[
            {"id":"one", "due_at":"due"}, {"id":"two", "due_at":"older"}
        ]});
        assert!(ledger.unseen(&[refreshed.clone()]).unwrap().is_empty());
        ledger.remember_accepted(&[refreshed.clone()]).unwrap();
        assert_eq!(ledger.accepted_for(&[refreshed]).unwrap(), vec![original]);
        assert!(ledger.accepted_for(&[reminder("missing", "due")]).is_err());
    }

    #[test]
    fn os_rejection_does_not_consume_reminder_and_new_items_remain_deliverable() {
        let mut ledger = DeliveryLedger::default();
        let one = reminder("one", "due");
        assert_eq!(ledger.unseen(&[one.clone()]).unwrap().len(), 1);
        assert_eq!(ledger.unseen(&[one.clone()]).unwrap().len(), 1);
        ledger.remember_accepted(&[one.clone()]).unwrap();
        let two = reminder("two", "due");
        assert_eq!(ledger.unseen(&[one, two.clone()]).unwrap(), vec![two]);
        assert!(ledger.unseen(&[json!({"id":"broken"})]).is_err());
    }
}
