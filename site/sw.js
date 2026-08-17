/* Service worker del monitor: solo notificaciones push. Sin caché offline
   (el sitio es estático y se sirve fresco; el alcance es /site/). */
self.addEventListener("push", (event) => {
  let datos = {};
  try { datos = event.data ? event.data.json() : {}; } catch { /* texto plano */ }
  const titulo = datos.titulo || "Monitor de brechas";
  event.waitUntil(self.registration.showNotification(titulo, {
    body: datos.cuerpo || (event.data ? event.data.text() : ""),
    icon: "icons/icono-192.png",
    badge: "icons/icono-192.png",
    tag: "alertas-del-dia",   // una notificación por día: la nueva sustituye
    data: { url: datos.url || "/site/#alerts-section" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data || {}).url || "/site/";
  event.waitUntil(clients.matchAll({ type: "window" }).then((ventanas) => {
    for (const v of ventanas) {
      if (v.url.includes("/site/") && "focus" in v) return v.focus();
    }
    return clients.openWindow(url);
  }));
});
