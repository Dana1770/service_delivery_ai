{
    "name": "Smart Delivery AI",
    "version": "1.0",
    "summary": "تحديد موقع التوصيل ومقارنة التوقيع بالذكاء الاصطناعي",
    "depends": ["base", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/smart_delivery_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "smart_delivery_ai/static/src/js/location.js",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
