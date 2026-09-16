"""Deterministic circuit-style QR, keeping finder patterns and a four-module quiet zone."""
import hashlib

import qrcode


def art_svg(url: str) -> bytes:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    size = len(matrix)
    mid = size / 2
    variant = hashlib.sha256(url.encode()).digest()[0] % 2
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}">',
             f'<rect width="{size}" height="{size}" fill="white"/>', '<g fill="#713a42">']
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                # Preserve square functional patterns; round data into connected circuit tracks.
                finder = (x < 12 and y < 12) or (x >= size - 12 and y < 12) or (x < 12 and y >= size - 12)
                radius = 0 if finder else .22
                parts.append(f'<rect x="{x}" y="{y}" width="1" height="1" rx="{radius}"/>')
    parts.extend(['</g>', f'<g transform="translate({mid - 4} {mid - 3})">',
                  '<rect width="8" height="6" rx="1" fill="white"/>'])
    if variant:
        # Smart vehicle: body, windscreen, wheels.
        parts.append('<g fill="#713a42"><path d="M1 3 2 1.5h4L7 3v1.5H1z"/><circle cx="2" cy="4.5" r=".6"/><circle cx="6" cy="4.5" r=".6"/></g><path d="M2.6 2h2.8l.5 1H2.1z" fill="white"/>')
    else:
        # Quadcopter: four rotors and diagonal arms.
        parts.append('<g stroke="#713a42" stroke-width=".45" fill="none"><path d="m2 1.5 4 3m0-3-4 3"/><ellipse cx="2" cy="1.5" rx="1.2" ry=".65"/><ellipse cx="6" cy="1.5" rx="1.2" ry=".65"/><ellipse cx="2" cy="4.5" rx="1.2" ry=".65"/><ellipse cx="6" cy="4.5" rx="1.2" ry=".65"/></g><rect x="3.25" y="2" width="1.5" height="2" rx=".5" fill="#713a42"/>')
    parts.append('</g></svg>')
    return ''.join(parts).encode()
