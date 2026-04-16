# -*- coding: utf-8 -*-
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SmartDeliveryController(http.Controller):

    @http.route(
        "/smart_delivery/save_location",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=False,
    )
    def save_location(self, record_id, lat, lng, **kwargs):
        """
        Receives GPS coordinates from the browser JS and saves them
        on the smart.delivery record.
        """
        try:
            record = request.env["smart.delivery"].browse(int(record_id))
            if not record.exists():
                return {"success": False, "error": "Record not found"}
            record.sudo().write({"current_lat": lat, "current_lng": lng})
            return {"success": True, "lat": lat, "lng": lng}
        except Exception as e:
            _logger.exception("Error saving location")
            return {"success": False, "error": str(e)}
