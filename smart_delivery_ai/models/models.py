from fastapi import FastAPI
import base64
import numpy as np
import cv2

app = FastAPI()


def decode_image(base64_str):
    img_data = base64.b64decode(base64_str)
    np_arr = np.frombuffer(img_data, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)


@app.post("/compare-signature")
def compare_signature(data: dict):
    img1 = decode_image(data["sig1"])
    img2 = decode_image(data["sig2"])

    img1 = cv2.resize(img1, (300, 150))
    img2 = cv2.resize(img2, (300, 150))

    diff = cv2.absdiff(img1, img2)
    score = 1 - (np.sum(diff) / (300 * 150 * 255))

    return {
        "match": score > 0.7,
        "confidence": float(score)
    }