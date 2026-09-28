import io
import os
import re
import secrets
import unicodedata
from collections import Counter
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from flask_sqlalchemy import SQLAlchemy
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import or_
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
url = os.getenv('DATABASE_URL', 'sqlite:///respel.db')
app.config['SQLALCHEMY_DATABASE_URI'] = url.replace('postgres://', 'postgresql://', 1) if url.startswith('postgres://') else url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('RENDER', '').lower() == 'true'
db = SQLAlchemy(app)
FIELDS = [('cliente', 'Clientes RESPEL'), ('contacto', 'Nombre contacto'), ('telefono', 'Teléfono'), ('correo', 'Correo'), ('direccion', 'Dirección'), ('tipo_residuo', 'Tipo de residuo'), ('estado', 'Estado de solicitud')]
ALIASES = {'clientes respel': 'cliente', 'cliente respel': 'cliente', 'cliente': 'cliente', 'nombre contacto': 'contacto', 'contacto': 'contacto', 'telefono': 'telefono', 'correo': 'correo', 'email': 'correo', 'direccion': 'direccion', 'tipo de residuo': 'tipo_residuo', 'tipo residuo': 'tipo_residuo', 'estado de solicitud': 'estado', 'estado solicitud': 'estado'}

class Solicitud(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente = db.Column(db.String(200), nullable=False)
    contacto = db.Column(db.String(200), default='')
    telefono = db.Column(db.String(200), default='')
    correo = db.Column(db.String(200), default='')
    direccion = db.Column(db.String(300), default='')
    tipo_residuo = db.Column(db.String(300), default='')
    estado = db.Column(db.String(200), default='')

with app.app_context():
    db.create_all()

def norm(value):
    decomposed = unicodedata.normalize('NFKD', str(value or '').lower())
    return re.sub(r'\s+', ' ', ''.join(c for c in decomposed if not unicodedata.combining(c)).replace('*', '').strip())

def priority(row):
    state, kind = norm(row.estado), norm(row.tipo_residuo)
    if any(x in state for x in ('cerrado', 'completado', 'finalizado', 'cancelado', 'no interesado')):
        return 'Cerrada'
    if (any(x in kind for x in ('peligroso', 'asbesto', 'quimic', 'contaminad', 'reas')) and 'no peligroso' not in kind) or any(x in state for x in ('urgente', 'pendiente', 'esperando', 'sin respuesta', 'por contactar')):
        return 'Alta'
    if any(x in state for x in ('cotizacion', 'agendar', 'visita', 'llamar', 'seguimiento')):
        return 'Media'
    return 'Baja'

def auth(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped

@app.before_request
def csrf_check():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(24)
    if request.method == 'POST' and request.form.get('csrf') != session['csrf']:
        abort(400, 'Recarga el formulario e inténtalo nuevamente.')

@app.context_processor
def context():
    return dict(fields=FIELDS, csrf=session.get('csrf'), priority=priority)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user, hashed = os.getenv('APP_USER', ''), os.getenv('APP_PASSWORD_HASH', '')
        if user and hashed and secrets.compare_digest(request.form.get('username', ''), user) and check_password_hash(hashed, request.form.get('password', '')):
            session.clear()
            session.update(logged_in=True, csrf=secrets.token_hex(24))
            return redirect(url_for('dashboard'))
        flash('Credenciales incorrectas o acceso aún no configurado.', 'error')
    return render_template('login.html')

@app.post('/logout')
@auth
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.get('/')
@auth
def dashboard():
    rows = Solicitud.query.order_by(Solicitud.id.desc()).all()
    levels = Counter(priority(r) for r in rows)
    states = Counter(r.estado.strip() or 'Sin estado' for r in rows)
    kinds = Counter(r.tipo_residuo.strip() or 'Sin tipo' for r in rows)
    insights = ['Aún no hay solicitudes. Importa una planilla o crea un registro.'] if not rows else [f'{levels["Alta"]} de {len(rows)} solicitudes tienen prioridad alta ({levels["Alta"] / len(rows):.0%}).', f'Estado más frecuente: {states.most_common(1)[0][0]} ({states.most_common(1)[0][1]}).', f'Tipo de residuo más frecuente: {kinds.most_common(1)[0][0]} ({kinds.most_common(1)[0][1]}).']
    return render_template('dashboard.html', total=len(rows), levels=levels, states=states.most_common(8), kinds=kinds.most_common(8), urgent=[r for r in rows if priority(r) == 'Alta'][:7], insights=insights)

@app.get('/solicitudes')
@auth
def listing():
    q = request.args.get('q', '').strip()[:100]
    level = request.args.get('prioridad', '')
    query = Solicitud.query
    if q:
        query = query.filter(or_(*(getattr(Solicitud, f).ilike(f'%{q}%') for f, _ in FIELDS)))
    rows = query.order_by(Solicitud.id.desc()).all()
    if level in ('Alta', 'Media', 'Baja', 'Cerrada'):
        rows = [r for r in rows if priority(r) == level]
    return render_template('list.html', rows=rows[:500], count=len(rows), q=q, level=level)

def values():
    data = {f: request.form.get(f, '').strip() for f, _ in FIELDS}
    if not data['cliente']:
        raise ValueError('El cliente es obligatorio.')
    if any(len(data[f]) > (300 if f in ('direccion', 'tipo_residuo') else 200) for f, _ in FIELDS):
        raise ValueError('Un campo supera el largo permitido.')
    return data

@app.route('/solicitudes/nueva', methods=['GET', 'POST'])
@auth
def create():
    if request.method == 'POST':
        try:
            db.session.add(Solicitud(**values()))
            db.session.commit()
            flash('Solicitud guardada.', 'success')
            return redirect(url_for('listing'))
        except ValueError as exc:
            flash(str(exc), 'error')
    return render_template('form.html', row=None)

@app.route('/solicitudes/<int:identifier>/editar', methods=['GET', 'POST'])
@auth
def edit(identifier):
    row = db.get_or_404(Solicitud, identifier)
    if request.method == 'POST':
        try:
            for key, value in values().items():
                setattr(row, key, value)
            db.session.commit()
            flash('Solicitud actualizada.', 'success')
            return redirect(url_for('listing'))
        except ValueError as exc:
            flash(str(exc), 'error')
    return render_template('form.html', row=row)

@app.post('/solicitudes/<int:identifier>/eliminar')
@auth
def delete(identifier):
    db.session.delete(db.get_or_404(Solicitud, identifier))
    db.session.commit()
    flash('Solicitud eliminada.', 'success')
    return redirect(url_for('listing'))

def excel(rows):
    book = Workbook()
    sheet = book.active
    sheet.title = 'Solicitudes'
    sheet.append([label for _, label in FIELDS])
    for row in rows:
        sheet.append([getattr(row, key) or '' for key, _ in FIELDS])
    for cell in sheet[1]:
        cell.fill = PatternFill('solid', fgColor='164735')
        cell.font = Font(color='FFFFFF', bold=True)
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = 28
    stream = io.BytesIO()
    book.save(stream)
    stream.seek(0)
    return stream

MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

@app.get('/plantilla.xlsx')
@auth
def template():
    return send_file(excel([]), as_attachment=True, download_name='plantilla_respel.xlsx', mimetype=MIME)

@app.get('/exportar.xlsx')
@auth
def export():
    return send_file(excel(Solicitud.query.order_by(Solicitud.id).all()), as_attachment=True, download_name='solicitudes_respel.xlsx', mimetype=MIME)

@app.route('/importar', methods=['GET', 'POST'])
@auth
def import_excel():
    if request.method == 'POST':
        file = request.files.get('archivo')
        if not file or not file.filename.lower().endswith('.xlsx'):
            flash('Selecciona un archivo .xlsx.', 'error')
        else:
            try:
                book = load_workbook(io.BytesIO(file.read()), read_only=True, data_only=True)
                sheet = book.active
                iterator = sheet.iter_rows(values_only=True)
                header = next(iterator, None)
                if not header:
                    raise ValueError('La hoja está vacía.')
                mapping = {}
                for i, value in enumerate(header):
                    key = ALIASES.get(norm(value))
                    if key and key not in mapping:
                        mapping[key] = i
                if 'cliente' not in mapping or len(mapping) < 2:
                    raise ValueError('Se requiere Cliente RESPEL y al menos otra columna reconocida. Descarga la plantilla.')
                added = skipped = 0
                for number, cells in enumerate(iterator, 2):
                    if number > 10001:
                        raise ValueError('El máximo es 10.000 filas por archivo.')
                    data = {}
                    for field, _ in FIELDS:
                        index = mapping.get(field)
                        value = cells[index] if index is not None and index < len(cells) else None
                        data[field] = (str(value).strip() if value is not None else '')[:300 if field in ('direccion', 'tipo_residuo') else 200]
                    if not data['cliente']:
                        skipped += 1
                        continue
                    db.session.add(Solicitud(**data))
                    added += 1
                db.session.commit()
                book.close()
                flash(f'{added} registros agregados; {skipped} filas sin cliente omitidas. No se detectan duplicados.', 'success')
                return redirect(url_for('listing'))
            except Exception as exc:
                db.session.rollback()
                flash(str(exc) if isinstance(exc, ValueError) else 'No se pudo leer el archivo .xlsx.', 'error')
    return render_template('import.html')

@app.get('/health')
def health():
    return {'status': 'ok'}

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG') == '1')
