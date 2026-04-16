# -*- coding: utf-8 -*-
import math
import base64
import io
import logging

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SmartDelivery(models.Model):
    _name = "smart.delivery"
    _description = "Smart Delivery AI"
    _rec_name = "name"

    name = fields.Char(string="Reference", default="New", readonly=True)

    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
    )

    # ─── موقع العميل ───
    delivery_lat = fields.Float(string="Customer Latitude", digits=(10, 7))
    delivery_lng = fields.Float(string="Customer Longitude", digits=(10, 7))

    # ─── الموقع الحالي للمندوب ───
    current_lat = fields.Float(string="Current Latitude", digits=(10, 7))
    current_lng = fields.Float(string="Current Longitude", digits=(10, 7))

    # ─── نتيجة المقارنة الجغرافية ───
    distance = fields.Float(string="Distance (km)", readonly=True, digits=(10, 3))
    is_in_range = fields.Boolean(string="Within 200m Range", readonly=True)
    location_status = fields.Selection(
        [("pending", "Pending"), ("ok", "In Range ✅"), ("far", "Out of Range ❌")],
        string="Location Status",
        default="pending",
        readonly=True,
    )

    # ─── التواقيع ───
    signature = fields.Binary(string="Customer Signature (New)", attachment=True)
    saved_signature = fields.Binary(string="Reference Signature (Stored)", attachment=True)

    # ─── نتيجة مقارنة التوقيع ───
    signature_match = fields.Boolean(string="Signature Match", readonly=True)
    signature_confidence = fields.Float(string="Match Confidence %", readonly=True, digits=(5, 2))
    signature_status = fields.Selection(
        [("pending", "Not Compared"), ("match", "Match ✅"), ("nomatch", "No Match ❌")],
        string="Signature Status",
        default="pending",
        readonly=True,
    )

    # ─── صورة التحقق من الهوية ───
    customer_photo = fields.Binary(
        string="Customer Photo (Taken at Delivery)",
        attachment=True,
        help="صورة يلتقطها المندوب للزبون عند التسليم للتحقق من الهوية",
    )
    reference_photo = fields.Binary(
        string="Reference Photo (ID / Profile)",
        attachment=True,
        help="الصورة المرجعية للزبون من ملفه أو هويته",
    )

    # ─── نتيجة مقارنة الصورة ───
    photo_match = fields.Boolean(string="Photo Match", readonly=True)
    photo_confidence = fields.Float(string="Photo Match Confidence %", readonly=True, digits=(5, 2))
    photo_status = fields.Selection(
        [("pending", "Not Compared"), ("match", "Match ✅"), ("nomatch", "No Match ❌")],
        string="Photo Verification Status",
        default="pending",
        readonly=True,
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("delivered", "Delivered"),
            ("failed", "Failed"),
        ],
        string="Status",
        default="draft",
    )


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("smart.delivery") or "New"
        return super().create(vals_list)


    def _haversine(self, lat1, lon1, lat2, lon2):
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def action_check_location(self):
        for rec in self:
            if not rec.current_lat or not rec.current_lng:
                raise UserError("الموقع الحالي غير محدد. اضغط على 'تحديد موقعي' أولاً.")
            if not rec.delivery_lat or not rec.delivery_lng:
                raise UserError("موقع العميل غير محدد. أدخل خطوط الطول والعرض للعميل.")
            dist = rec._haversine(rec.current_lat, rec.current_lng, rec.delivery_lat, rec.delivery_lng)
            rec.distance = dist
            in_range = dist <= 0.2
            rec.is_in_range = in_range
            rec.location_status = "ok" if in_range else "far"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Location Check",
                "message": f"Distance: {self.distance:.3f} km — {'✅ In Range' if self.is_in_range else '❌ Out of Range'}",
                "type": "success" if self.is_in_range else "warning",
                "sticky": False,
            },
        }


    @staticmethod
    def _otsu_threshold(histogram, total_pixels):
        best_threshold = 128
        best_variance = 0.0
        cumulative_weight = 0
        cumulative_mean = 0.0
        total_mean = sum(i * histogram[i] for i in range(256)) / max(total_pixels, 1)
        for t in range(256):
            cumulative_weight += histogram[t]
            if cumulative_weight == 0:
                continue
            background_weight = cumulative_weight / total_pixels
            foreground_weight = 1.0 - background_weight
            if foreground_weight == 0:
                break
            cumulative_mean += t * histogram[t]
            background_mean = cumulative_mean / cumulative_weight
            foreground_mean = (total_mean - background_weight * background_mean) / foreground_weight
            between_variance = background_weight * foreground_weight * (background_mean - foreground_mean) ** 2
            if between_variance > best_variance:
                best_variance = between_variance
                best_threshold = t
        return best_threshold

    def _load_and_normalize_signature(self, b64, target_size=(256, 128)):
        try:
            from PIL import Image, ImageOps, ImageFilter
        except ImportError:
            raise UserError("Pillow is not installed. Run: pip install Pillow")

        data = base64.b64decode(b64)
        img = Image.open(io.BytesIO(data))

        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"):
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        else:
            img = img.convert("RGB")

        img = img.convert("L")
        img = ImageOps.autocontrast(img, cutoff=2)
        img = img.filter(ImageFilter.GaussianBlur(radius=1.0))

        histogram = img.histogram()
        threshold = self._otsu_threshold(histogram, img.width * img.height)

        pixels = list(img.getdata())
        binary = [0 if p < threshold else 255 for p in pixels]
        img.putdata(binary)

        width, height = img.size
        min_x, min_y = width, height
        max_x, max_y = 0, 0
        has_ink = False
        for y in range(height):
            for x in range(width):
                if binary[y * width + x] == 0:
                    if x < min_x: min_x = x
                    if x > max_x: max_x = x
                    if y < min_y: min_y = y
                    if y > max_y: max_y = y
                    has_ink = True

        if has_ink and max_x > min_x and max_y > min_y:
            pad = max(6, int(min(width, height) * 0.04))
            img = img.crop((max(0, min_x - pad), max(0, min_y - pad),
                            min(width, max_x + pad), min(height, max_y + pad)))

        return img.resize(target_size, Image.LANCZOS)

    def _compare_signatures(self, b64_img1, b64_img2):
        TARGET_SIZE = (256, 128)
        INK = 0

        img1 = self._load_and_normalize_signature(b64_img1, TARGET_SIZE)
        img2 = self._load_and_normalize_signature(b64_img2, TARGET_SIZE)
        pixels1 = list(img1.getdata())
        pixels2 = list(img2.getdata())
        total = len(pixels1)
        W, H = TARGET_SIZE

        # Metric 1: Pixel similarity
        diff_sum = sum(abs(p1 - p2) for p1, p2 in zip(pixels1, pixels2))
        pixel_score = 1.0 - (diff_sum / (total * 255.0))

        # Metric 2: Jaccard ink overlap
        ink1 = {i for i, p in enumerate(pixels1) if p == INK}
        ink2 = {i for i, p in enumerate(pixels2) if p == INK}
        if ink1 or ink2:
            jaccard = len(ink1 & ink2) / len(ink1 | ink2)
        else:
            jaccard = 1.0

        # Metric 3: Projection profiles
        def h_profile(px, w, h):
            return [sum(1 for x in range(w) if px[r * w + x] == INK) / w for r in range(h)]

        def v_profile(px, w, h):
            return [sum(1 for y in range(h) if px[y * w + c] == INK) / h for c in range(w)]

        def prof_sim(p1, p2):
            return 1.0 - sum(abs(a - b) for a, b in zip(p1, p2)) / len(p1)

        projection_score = (prof_sim(h_profile(pixels1, W, H), h_profile(pixels2, W, H)) +
                            prof_sim(v_profile(pixels1, W, H), v_profile(pixels2, W, H))) / 2.0

        combined = 0.25 * pixel_score + 0.50 * jaccard + 0.25 * projection_score
        confidence = round(combined * 100, 2)
        match = combined >= 0.58

        _logger.info(
            "Signature — pixel=%.3f jaccard=%.3f projection=%.3f combined=%.3f match=%s",
            pixel_score, jaccard, projection_score, combined, match,
        )
        return match, confidence

    def action_compare_signature(self):
        for rec in self:
            if not rec.signature:
                raise UserError("لم يتم رفع التوقيع الجديد للعميل بعد.")
            if not rec.saved_signature:
                raise UserError("لا يوجد توقيع مرجعي محفوظ. استخدم 'حفظ كتوقيع مرجعي' أولاً.")
            match, confidence = rec._compare_signatures(rec.signature, rec.saved_signature)
            rec.signature_match = match
            rec.signature_confidence = confidence
            rec.signature_status = "match" if match else "nomatch"

        msg = (f"✅ التوقيعان متطابقان — {self.signature_confidence:.1f}%"
               if self.signature_match
               else f"❌ التوقيعان غير متطابقين — {self.signature_confidence:.1f}%")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "نتيجة مقارنة التوقيع", "message": msg,
                       "type": "success" if self.signature_match else "danger", "sticky": True},
        }

    def action_save_as_reference(self):
        for rec in self:
            if not rec.signature:
                raise UserError("لا يوجد توقيع جديد لحفظه كمرجع.")
            rec.saved_signature = rec.signature
            rec.signature_status = "pending"
            rec.signature_match = False
            rec.signature_confidence = 0.0
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "تم الحفظ", "message": "✅ تم حفظ التوقيع كتوقيع مرجعي.",
                       "type": "success", "sticky": False},
        }

    def _compare_photos(self, b64_photo1, b64_photo2):
        try:
            from PIL import Image, ImageFilter
        except ImportError:
            raise UserError("Pillow is not installed. Run: pip install Pillow")

        TARGET_SIZE = (128, 128)
        GRID = 8

        def load_photo(b64):
            data = base64.b64decode(b64)
            img = Image.open(io.BytesIO(data))
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            else:
                img = img.convert("RGB")
            img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
            return img.resize(TARGET_SIZE, Image.LANCZOS)

        img1 = load_photo(b64_photo1)
        img2 = load_photo(b64_photo2)

        # Metric 1: Color histogram similarity (Bhattacharyya coefficient)
        hist_scores = []
        for ch in range(3):
            h1 = img1.split()[ch].histogram()
            h2 = img2.split()[ch].histogram()
            s1, s2 = sum(h1), sum(h2)
            if s1 == 0 or s2 == 0:
                continue
            n1 = [v / s1 for v in h1]
            n2 = [v / s2 for v in h2]
            hist_scores.append(sum((a * b) ** 0.5 for a, b in zip(n1, n2)))
        hist_score = sum(hist_scores) / len(hist_scores) if hist_scores else 0.0

        # Metric 2: Spatial block pixel similarity
        px1 = list(img1.getdata())
        px2 = list(img2.getdata())
        W = TARGET_SIZE[0]
        bw = bh = W // GRID
        block_scores = []
        for gy in range(GRID):
            for gx in range(GRID):
                diffs = []
                for by in range(bh):
                    for bx in range(bw):
                        idx = (gy * bh + by) * W + (gx * bw + bx)
                        if idx < len(px1):
                            p1, p2 = px1[idx], px2[idx]
                            diffs.append(sum(abs(p1[c] - p2[c]) for c in range(3)) / (3 * 255.0))
                if diffs:
                    block_scores.append(1.0 - (sum(diffs) / len(diffs)))
        spatial_score = sum(block_scores) / len(block_scores) if block_scores else 0.0

        combined = 0.45 * hist_score + 0.55 * spatial_score
        confidence = round(combined * 100, 2)
        match = combined >= 0.65

        _logger.info(
            "Photo — hist=%.3f spatial=%.3f combined=%.3f match=%s",
            hist_score, spatial_score, combined, match,
        )
        return match, confidence

    def action_compare_photo(self):
        for rec in self:
            if not rec.customer_photo:
                raise UserError("لم يتم التقاط صورة الزبون بعد.")
            if not rec.reference_photo:
                raise UserError("لا توجد صورة مرجعية للزبون. ارفع صورة الهوية أو المرجعية أولاً.")
            match, confidence = rec._compare_photos(rec.customer_photo, rec.reference_photo)
            rec.photo_match = match
            rec.photo_confidence = confidence
            rec.photo_status = "match" if match else "nomatch"

        msg = (f"✅ الصورة مطابقة — {self.photo_confidence:.1f}%"
               if self.photo_match
               else f"❌ الصورة غير مطابقة — {self.photo_confidence:.1f}%")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "نتيجة التحقق من الهوية بالصورة", "message": msg,
                       "type": "success" if self.photo_match else "danger", "sticky": True},
        }

    def action_save_reference_photo(self):
        for rec in self:
            if not rec.customer_photo:
                raise UserError("لا توجد صورة لحفظها كمرجع.")
            rec.reference_photo = rec.customer_photo
            rec.photo_status = "pending"
            rec.photo_match = False
            rec.photo_confidence = 0.0
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "تم الحفظ", "message": "✅ تم حفظ الصورة كصورة مرجعية.",
                       "type": "success", "sticky": False},
        }


    def action_start(self):
        self.state = "in_progress"

    def action_deliver(self):
        if not self.signature:
            raise UserError("يجب الحصول على توقيع العميل قبل تأكيد التسليم.")
        if not self.current_lat or not self.current_lng:
            raise UserError("الموقع الحالي غير محدد. اضغط على تحديد موقعي أولاً.")
        if not self.delivery_lat or not self.delivery_lng:
            raise UserError("موقع العميل غير محدد. أدخل إحداثيات العميل أولاً.")
        self.action_check_location()
        if not self.is_in_range:
            raise UserError(
                f"أنت خارج نطاق 200 متر من موقع العميل (المسافة: {self.distance:.3f} كم)."
            )
        if self.saved_signature:
            match, confidence = self._compare_signatures(self.signature, self.saved_signature)
            self.signature_match = match
            self.signature_confidence = confidence
            self.signature_status = "match" if match else "nomatch"
            if not match:
                raise UserError(
                    f"التوقيع غير متطابق مع المرجع ({confidence:.1f}%). تعذر تأكيد التسليم."
                )
        if self.customer_photo and self.reference_photo:
            photo_match, photo_conf = self._compare_photos(self.customer_photo, self.reference_photo)
            self.photo_match = photo_match
            self.photo_confidence = photo_conf
            self.photo_status = "match" if photo_match else "nomatch"
            if not photo_match:
                raise UserError(
                    f"صورة الزبون لا تتطابق مع الصورة المرجعية ({photo_conf:.1f}%). تعذر تأكيد التسليم."
                )
        self.state = "delivered"

    def action_fail(self):
        self.state = "failed"

    def action_reset(self):
        self.state = "draft"

    def action_get_location_js(self):
        return {
            "type": "ir.actions.client",
            "tag": "smart_delivery_get_location",
            "context": {"active_id": self.id},
        }
