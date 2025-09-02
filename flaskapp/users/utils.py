from flask import url_for, current_app
from flask_mail import Message
from flaskapp import mail
import os, secrets
from PIL import Image, ExifTags, ImageOps

def save_picture(form_picture, size=(256, 256)):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename or "")
    picture_fn = random_hex + '.jpg'
    picture_path = os.path.join(current_app.root_path, 'static/profile_pics', picture_fn)
    img = Image.open(form_picture)

    try:
        exif = img._getexif()
        if exif:
            orientation_key = next((k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)
            if orientation_key and orientation_key in exif:
                orientation = exif[orientation_key]
                rotate_map = {3: 180, 6: 270, 8: 90}
                if orientation in rotate_map:
                    img = img.rotate(rotate_map[orientation], expand=True)
    except Exception:
        pass

    img = img.convert('RGB')
    img = ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, 0.5))
    img.save(picture_path, format='JPEG', quality=85, optimize=True)
    return picture_fn


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request',
                  sender='noreply@demo.com',
                  recipients=[user.email])
    msg.body = f'''To reset your password, visit the following link: {url_for('users.reset_token', token=token, _external=True)} 
    If you did not make this request then simply ignore this email and no changes will be made.'''

    mail.send(msg)