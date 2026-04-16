/** @odoo-module **/
/**
 * Smart Delivery AI — GPS Location
 *
 * Strategy:
 *  1. Try browser Geolocation API (accurate, works on HTTPS or allowed HTTP)
 *  2. If blocked (HTTP/localhost), fall back to IP geolocation via ipapi.co
 *  3. Show clear Arabic messages at every step
 */

import { registry } from "@web/core/registry";

// ── Try browser GPS ──────────────────────────────────────────────────────────
function getBrowserPosition() {
    return new Promise((resolve, reject) => {
        if (!navigator.geolocation) {
            reject({ code: -1, message: "no_api" });
            return;
        }
        navigator.geolocation.getCurrentPosition(resolve, reject, {
            enableHighAccuracy: true,
            timeout: 12000,
            maximumAge: 0,
        });
    });
}

// ── IP-based fallback (no permission needed, ~city-level accuracy) ───────────
async function getIPPosition() {
    const res = await fetch("https://ipapi.co/json/", { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error("IP geolocation failed");
    const data = await res.json();
    if (!data.latitude || !data.longitude) throw new Error("No coordinates in IP response");
    return { latitude: data.latitude, longitude: data.longitude, source: "ip" };
}

// ── Main action ──────────────────────────────────────────────────────────────
const getLocationAction = async (env, action) => {
    const notification = env.services.notification;
    const orm = env.services.orm;

    const activeId = action.context && action.context.active_id;
    if (!activeId) {
        notification.add("❌ احفظ السجل أولاً قبل تحديد الموقع.", { type: "danger" });
        return;
    }

    notification.add("📡 جاري تحديد موقعك…", { type: "info" });

    let lat, lng, source = "gps";

    // ── Attempt 1: Browser GPS ───────────────────────────────────────────────
    try {
        const position = await getBrowserPosition();
        lat = position.coords.latitude;
        lng = position.coords.longitude;
        source = "gps";
    } catch (gpsErr) {
        // GPS failed — try IP fallback
        const isDenied = gpsErr.code === 1;
        const isHTTP = window.location.protocol === "http:";

        let fallbackMsg = isDenied && isHTTP
            ? "⚠️ تعذّر GPS على HTTP. جاري استخدام الموقع التقريبي عبر الإنترنت…"
            : "⚠️ تعذّر GPS. جاري المحاولة عبر الإنترنت…";

        notification.add(fallbackMsg, { type: "warning" });

        // ── Attempt 2: IP Geolocation ────────────────────────────────────────
        try {
            const ipPos = await getIPPosition();
            lat = ipPos.latitude;
            lng = ipPos.longitude;
            source = "ip";
        } catch (ipErr) {
            // Both failed — show final error with guidance
            let finalMsg;
            if (gpsErr.code === 1) {
                finalMsg =
                    "🔒 تم رفض إذن الموقع ولم يتوفر اتصال بالإنترنت للحصول على الموقع التقريبي.\n" +
                    "لتفعيل GPS:\n" +
                    "• Chrome: افتح chrome://flags ← ابحث عن 'Insecure origins' ← أضف http://localhost:8087 ← أعد تشغيل Chrome\n" +
                    "• أو استخدم HTTPS لتشغيل Odoo.";
            } else if (gpsErr.code === 2) {
                finalMsg = "❌ GPS غير متاح وفشل الاتصال بالإنترنت. تأكد من اتصالك.";
            } else if (gpsErr.code === 3) {
                finalMsg = "⏱️ انتهت مهلة GPS. حاول مرة أخرى.";
            } else {
                finalMsg = `❌ فشل تحديد الموقع: ${gpsErr.message || gpsErr.code}`;
            }
            notification.add(finalMsg, { type: "danger", sticky: true });
            return;
        }
    }

    // ── Save coordinates ─────────────────────────────────────────────────────
    try {
        await orm.write("smart.delivery", [activeId], {
            current_lat: lat,
            current_lng: lng,
        });

        const sourceLabel = source === "ip"
            ? " (موقع تقريبي عبر IP — للدقة استخدم HTTPS)"
            : "";

        notification.add(
            `✅ تم تحديد موقعك: ${lat.toFixed(6)}, ${lng.toFixed(6)}${sourceLabel}`,
            { type: source === "ip" ? "warning" : "success" }
        );

        env.services.action.doAction({ type: "ir.actions.client", tag: "reload" });

    } catch (writeErr) {
        notification.add(`❌ فشل حفظ الموقع: ${writeErr.message}`, {
            type: "danger", sticky: true,
        });
    }
};

registry.category("actions").add("smart_delivery_get_location", getLocationAction);
