from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from flask import Flask, jsonify
from routes.profile_photo import profile_photo_bp
from services.profile_photo import normalize_profile_photo, MAX_UPLOAD_BYTES

USER = '11111111-1111-4111-8111-111111111111'


def image_bytes(size=(120, 100), fmt='PNG'):
    output = BytesIO()
    Image.new('RGB', size, '#12628b').save(output, fmt)
    return output.getvalue()


class ProfilePhotoTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = 'synthetic-test-only'
        self.app.register_blueprint(profile_photo_bp)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state['profile_photo_csrf'] = 'synthetic-csrf'
        self.context = dict(user_id=USER, funcionario_id=USER, empresa_id=USER,
                            perfil='funcionario', session_id='synthetic', familia_id='synthetic')
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value = None

    def call(self, method='get', path='/api/perfil/foto', data=None, token='synthetic-csrf'):
        with patch('utils.auth_decorator._load_persistent_authentication', return_value=(self.context, None)), patch('routes.profile_photo.conectar_bd', return_value=self.connection):
            return getattr(self.client, method)(path, data=data, headers={'X-Profile-Token':token})

    def test_reencodes_and_strips_metadata(self):
        source = Image.new('RGB', (600, 900), '#155c88')
        exif = Image.Exif(); exif[270] = 'synthetic-private-metadata'
        buffer = BytesIO(); source.save(buffer, 'JPEG', exif=exif)
        result = normalize_profile_photo(buffer.getvalue())
        with Image.open(BytesIO(result)) as photo:
            self.assertEqual(photo.format, 'JPEG')
            self.assertEqual(photo.size, (512,512))
            self.assertFalse(photo.getexif())
        self.assertNotIn(b'synthetic-private-metadata', result)
        self.assertLessEqual(len(result), 262144)

    def test_rejects_invalid_small_oversize_animated_and_unsupported(self):
        frames = [Image.new('RGB',(100,100),'red'), Image.new('RGB',(100,100),'blue')]
        animation = BytesIO(); frames[0].save(animation,'WEBP',save_all=True,append_images=frames[1:])
        for invalid in [b'', b'<svg onload="alert(1)"></svg>', b'x'*(MAX_UPLOAD_BYTES+1), image_bytes((20,20)), image_bytes(fmt='GIF'), animation.getvalue(), image_bytes((4100,4000))]:
            with self.subTest(size=len(invalid)), self.assertRaises(ValueError):
                normalize_profile_photo(invalid)

    def test_unauthenticated_and_csrf_cannot_access_database(self):
        with self.app.app_context():
            error = (jsonify(erro='Auth'),401)
        with patch('utils.auth_decorator._load_persistent_authentication', return_value=(None,error)), patch('routes.profile_photo.conectar_bd') as connect:
            self.assertEqual(self.client.get('/api/perfil/foto').status_code,401)
            connect.assert_not_called()
        for method in ['put','delete']:
            self.assertEqual(self.call(method,token='wrong').status_code,403)
        self.connection.cursor.assert_not_called()

    def test_scoped_to_own_user_and_no_shared_cache(self):
        self.cursor.fetchone.return_value = (memoryview(image_bytes()),)
        response = self.call()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content_type,'image/jpeg')
        self.assertEqual(response.headers['Cache-Control'],'private, no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(self.cursor.execute.call_args.args[1],(USER,))
        self.assertEqual(self.call(path='/api/perfil/foto?usuario_id=other').status_code,400)

    def test_replace_and_remove_one_row_and_close_connection(self):
        response = self.call('put',data=image_bytes())
        self.assertEqual(response.status_code,200)
        sql,args = self.cursor.execute.call_args.args
        self.assertIn('ON CONFLICT (usuario_id) DO UPDATE',sql)
        self.assertEqual(args[0],USER)
        self.connection.commit.assert_called_once()
        self.connection.close.assert_called_once()
        self.connection.reset_mock()
        self.assertEqual(self.call('delete').status_code,200)
        self.assertEqual(self.cursor.execute.call_args.args,('DELETE FROM fotos_perfil WHERE usuario_id=%s',(USER,)))
        self.connection.commit.assert_called_once()

    def test_no_photo_and_unavailable_database(self):
        self.assertEqual(self.call().status_code,204)
        self.cursor.execute.side_effect = RuntimeError('synthetic')
        response = self.call('put',data=image_bytes())
        self.assertEqual(response.status_code,503)
        self.connection.rollback.assert_called_once()
        self.assertNotIn(b'synthetic',response.data)

    def test_invalid_file_never_opens_database(self):
        self.assertEqual(self.call('put',data=b'not-a-photo').status_code,400)
        self.assertEqual(self.call('put',data=b'x'*(MAX_UPLOAD_BYTES+1)).status_code,413)
        self.connection.cursor.assert_not_called()


if __name__ == '__main__':
    unittest.main()
