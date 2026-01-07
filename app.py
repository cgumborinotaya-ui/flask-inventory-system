from flask import Flask, render_template, request, redirect, url_for, flash, Response, session, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import csv
import io
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from sqlalchemy import text
from sqlalchemy import desc
from pathlib import Path

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['MINISTRY_NAME'] = 'Ministry of Women Affairs, Community, Small & Medium Enterprises Development'
app.config['LOGO_STATIC_PATH'] = '/static/zim_logo.png'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=5)
app.config['UPLOAD_FOLDER'] = str((Path(app.instance_path) / 'uploads').resolve())
db = SQLAlchemy(app)

PROVINCE_DISTRICTS = {
    'Head Office': [],
    'Bulawayo': ['Bulawayo District'],
    'Harare': ['Harare District'],
    'Manicaland': ['Buhera', 'Chimanimani', 'Chipinge', 'Makoni', 'Mutare', 'Mutasa', 'Nyanga'],
    'Mashonaland Central': ['Bindura', 'Guruve', 'Mazowe', 'Mbire', 'Mount Darwin', 'Rushinga', 'Shamva'],
    'Mashonaland East': ['Chikomba', 'Goromonzi', 'Marondera', 'Murehwa', 'Mutoko', 'Seke', 'Uzumba-Maramba-Pfungwe', 'Wedza'],
    'Mashonaland West': ['Chegutu', 'Hurungwe', 'Kadoma', 'Kariba', 'Makonde', 'Mhondoro-Ngezi', 'Sanyati', 'Zvimba'],
    'Masvingo': ['Bikita', 'Chiredzi', 'Chivi', 'Gutu', 'Masvingo', 'Mwenezi', 'Zaka'],
    'Matabeleland North': ['Binga', 'Hwange', 'Lupane', 'Nkayi', 'Tsholotsho', 'Umguza'],
    'Matabeleland South': ['Beitbridge', 'Gwanda', 'Insiza', 'Matobo', 'Mangwe', 'Umzingwane'],
    'Midlands': ['Chirumhanzu', 'Gokwe North', 'Gokwe South', 'Kwekwe', 'Mberengwa', 'Shurugwi', 'Zvishavane', 'Gweru'],
}

ALLOWED_ASSET_STATUSES = ['In Use', 'In Stock', 'Broken', 'Lost / Stolen', 'Auctioned', 'Archived']
LOCKED_ASSET_STATUSES = ['Archived', 'Auctioned']

class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    serial_number = db.Column(db.String(100), unique=True, nullable=False)
    purchase_date = db.Column(db.Date, nullable=True)
    assigned_to = db.Column(db.String(100), nullable=True)
    supplier = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(50), default='In Stock')
    acquisition_type = db.Column(db.String(20), nullable=True)
    donor_name = db.Column(db.String(120), nullable=True)
    capture_date = db.Column(db.Date, nullable=True)
    
    # New fields
    antivirus_name = db.Column(db.String(100), nullable=True)
    antivirus_license_date = db.Column(db.Date, nullable=True)
    office_name = db.Column(db.String(100), nullable=True)
    office_license_date = db.Column(db.Date, nullable=True)
    os_name = db.Column(db.String(100), nullable=True)
    province = db.Column(db.String(100), nullable=True)
    district = db.Column(db.String(100), nullable=True)
    inspected_by_ict = db.Column(db.Boolean, default=False)
    inspection_date = db.Column(db.Date, nullable=True)
    created_by_user_id = db.Column(db.Integer, nullable=True)

    @property
    def is_antivirus_expired(self):
        if not self.antivirus_license_date:
            return None
        # Check if license is older than 1 year (365 days)
        delta = datetime.now().date() - self.antivirus_license_date
        return delta.days > 365

    @property
    def is_office_expired(self):
        if not self.office_license_date:
            return None
        # Check if license is older than 1 year (365 days)
        delta = datetime.now().date() - self.office_license_date
        return delta.days > 365

    @property
    def eol_years(self):
        mapping = {
            'Laptop': 3,
            'Desktop': 5,
            'All-in-One': 5,
            'Cellphone': 2,
            'Tablet': 2,
        }
        return mapping.get(self.type)

    @property
    def eol_date(self):
        if not self.purchase_date or not self.eol_years:
            return None
        return self.purchase_date + timedelta(days=self.eol_years * 365)

    @property
    def is_eol_passed(self):
        if not self.eol_date:
            return None
        return datetime.now().date() >= self.eol_date

    @property
    def is_eol_approaching(self):
        if not self.eol_date:
            return None
        # 8 months ~ 240 days
        warning_threshold = self.eol_date - timedelta(days=240)
        today = datetime.now().date()
        return today >= warning_threshold and today < self.eol_date

    @property
    def eol_status(self):
        if not self.eol_date:
            return None
        if self.is_eol_passed:
            return 'Past End-of-Life'
        if self.is_eol_approaching:
            remaining_days = (self.eol_date - datetime.now().date()).days
            return f'Approaching EOL ({remaining_days} days left)'
        return f'EOL on {self.eol_date}'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    province = db.Column(db.String(100), nullable=True)  # 'Head Office' or specific province
    district = db.Column(db.String(100), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    email = db.Column(db.String(120), nullable=True)
    
from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()

    user = User.query.filter_by(username="admin").first()
    if not user:
        user = User(
            username="admin",
            password_hash=generate_password_hash("admin123"),
            role="admin"
        )
        db.session.add(user)
    else:
        user.password_hash = generate_password_hash("admin123")

    db.session.commit()


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)

def is_it():
    u = current_user()
    return bool(u and u.role == 'IT')

def has_asset_edit_rights():
    u = current_user()
    if not u:
        return False
    if u.role == 'IT':
        return True
    return u.role in ['Admin', 'AdminProvince', 'AdminDistrict']
def filter_by_user_location(query):
    u = current_user()
    if not u:
        return query
    if u.role == 'IT':
        return query
    if u.province == 'Head Office':
        return query
    q = query.filter(Asset.province == u.province)
    if u.district:
        if u.role == 'AdminDistrict':
            q = q.filter(Asset.district == u.district)
        else:
            if ',' not in (u.district or ''):
                q = q.filter(Asset.district == u.district)
    return q

@app.context_processor
def inject_user():
    return {
        'current_user': current_user(),
        'current_role': (current_user().role if current_user() else None),
        'ministry_name': app.config.get('MINISTRY_NAME'),
        'logo_url': app.config.get('LOGO_STATIC_PATH')
    }
class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    actor_user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)

class AssetActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(50), nullable=False)
    field = db.Column(db.String(80), nullable=True)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    details = db.Column(db.Text, nullable=True)

class AssetDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, nullable=True)
    doc_type = db.Column(db.String(50), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)

def log_action(action, entity_type=None, entity_id=None, details=None):
    try:
        entry = AuditLog(
            actor_user_id=current_user().id if current_user() else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass

def log_asset_activity(asset_id, action, field=None, old_value=None, new_value=None, details=None):
    try:
        entry = AssetActivity(
            asset_id=asset_id,
            actor_user_id=current_user().id if current_user() else None,
            action=action,
            field=field,
            old_value=old_value,
            new_value=new_value,
            details=details
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass

def send_email(to_email, subject, body):
    host = app.config.get('SMTP_HOST')
    port = app.config.get('SMTP_PORT')
    user = app.config.get('SMTP_USER')
    password = app.config.get('SMTP_PASS')
    from_email = app.config.get('FROM_EMAIL', user)
    if not (host and port and from_email):
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body, 'html')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email
        with smtplib.SMTP(host, port) as server:
            if user and password:
                server.starttls()
                server.login(user, password)
            server.send_message(msg)
        return True
    except Exception:
        return False

    def __repr__(self):
        return f'<Asset {self.name}>'

@app.route('/')
@login_required
def index():
    q = Asset.query
    q = filter_by_user_location(q)
    name_q = (request.args.get('name') or '').strip()
    serial_q = (request.args.get('serial') or '').strip()
    if name_q:
        q = q.filter(Asset.name.ilike(f"%{name_q}%"))
    if serial_q:
        q = q.filter(Asset.serial_number.ilike(f"%{serial_q}%"))
    all_assets = q.all()
    assets = [a for a in all_assets if (a.status or '').strip() not in LOCKED_ASSET_STATUSES]
    archived_auctioned_assets = [a for a in all_assets if (a.status or '').strip() in LOCKED_ASSET_STATUSES]
    stats = {
        'total': len(assets),
        'computers': sum(1 for a in assets if a.type in ['Laptop', 'Desktop', 'All-in-One']),
        'mobile': sum(1 for a in assets if a.type in ['Cellphone', 'Tablet']),
        'in_use': sum(1 for a in assets if a.status == 'In Use'),
        'uninspected': sum(1 for a in assets if not a.inspected_by_ict),
    }
    type_counts = {}
    for a in assets:
        type_counts[a.type] = type_counts.get(a.type, 0) + 1
    province_counts = {}
    for a in assets:
        if a.province:
            province_counts[a.province] = province_counts.get(a.province, 0) + 1
    top_provinces = sorted(province_counts.items(), key=lambda x: x[1], reverse=True)[:6]
    log_action('view_dashboard', details=f"name={name_q},serial={serial_q}")
    return render_template(
        'index.html',
        assets=assets,
        archived_auctioned_assets=archived_auctioned_assets,
        stats=stats,
        type_counts=type_counts,
        top_provinces=top_provinces,
        name_q=name_q,
        serial_q=serial_q,
    )

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_asset():
    if not has_asset_edit_rights():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = (request.form['name'] or '').strip()
        type = (request.form['type'] or '').strip()
        serial_number = (request.form['serial_number'] or '').strip()
        purchase_date_str = (request.form['purchase_date'] or '').strip()
        acquisition_type = (request.form.get('acquisition_type') or '').strip()
        donor_name = (request.form.get('donor_name') or '').strip()
        assigned_to = (request.form.get('assigned_to') or '').strip()
        supplier = (request.form.get('supplier') or '').strip()
        status = (request.form['status'] or '').strip()
        if status == 'Lost':
            status = 'Lost / Stolen'
        
        antivirus_name = request.form.get('antivirus_name')
        antivirus_license_date_str = request.form.get('antivirus_license_date')
        office_name = request.form.get('office_name')
        office_license_date_str = request.form.get('office_license_date')
        os_name = request.form.get('os_name')
        province = (request.form.get('province') or '').strip()
        district = (request.form.get('district') or '').strip()
        inspected_by_ict = True if request.form.get('inspected_by_ict') == 'on' else False
        inspection_date_str = request.form.get('inspection_date')
        loss_file = request.files.get('loss_evidence')
        specification_file = request.files.get('specification_document')
        inspection_file = request.files.get('inspection_document')

        u = current_user()
        if not is_it():
            antivirus_name = None
            antivirus_license_date_str = None
            office_name = None
            office_license_date_str = None
            os_name = None
        if u and u.role != 'IT':
            if u.province and u.province != 'Head Office':
                province = u.province
            if u.role == 'AdminDistrict' and u.district:
                district = u.district

        # Server-side validations
        errors = []
        if not name:
            errors.append('Asset name is required')
        if not type:
            errors.append('Asset type is required')
        if not serial_number:
            errors.append('Serial number is required')
        else:
            existing = Asset.query.filter_by(serial_number=serial_number).first()
            if existing:
                errors.append('Serial number already exists')
        if not purchase_date_str:
            errors.append('Purchase date is required')
        if not acquisition_type:
            errors.append('Acquisition Type is required')
        if acquisition_type not in ['Purchased', 'Donated']:
            errors.append('Invalid Acquisition Type selected')
        if acquisition_type == 'Purchased':
            if not supplier:
                errors.append('Supplier is required for purchased assets')
            if not specification_file or not specification_file.filename:
                errors.append('Procurement specification document is required for purchased assets')
        if acquisition_type == 'Donated':
            if not donor_name:
                errors.append('Donor Name is required for donated assets')
        if status not in ALLOWED_ASSET_STATUSES:
            errors.append('Invalid status selected')
        if status == 'In Use' and not assigned_to:
            errors.append('Assigned To is required when status is In Use')
        if status != 'In Use' and assigned_to:
            assigned_to = ''
        if status == 'Lost / Stolen' and (not loss_file or not loss_file.filename):
            errors.append('Police report / evidence document is required for Lost / Stolen assets')
        if is_it() and inspected_by_ict:
            if not inspection_date_str:
                errors.append('Inspection date is required when marking inspected')
            if not inspection_file or not inspection_file.filename:
                errors.append('Inspection document is required when marking inspected')
        if not province:
            errors.append('Province is required')
        elif province != 'Head Office' and not district:
            errors.append('District is required for the selected province')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('add_asset.html')

        try:
            purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date() if purchase_date_str else None
            antivirus_license_date = datetime.strptime(antivirus_license_date_str, '%Y-%m-%d').date() if antivirus_license_date_str else None
            office_license_date = datetime.strptime(office_license_date_str, '%Y-%m-%d').date() if office_license_date_str else None
            inspection_date = datetime.strptime(inspection_date_str, '%Y-%m-%d').date() if inspection_date_str else None
            
            if not is_it():
                inspected_by_ict = False
                inspection_date = None
            new_asset = Asset(
                name=name,
                type=type,
                serial_number=serial_number,
                purchase_date=purchase_date,
                assigned_to=assigned_to,
                status=status,
                supplier=(supplier or None),
                acquisition_type=acquisition_type,
                donor_name=(donor_name or None),
                capture_date=datetime.utcnow().date(),
                antivirus_name=antivirus_name,
                antivirus_license_date=antivirus_license_date,
                office_name=office_name,
                office_license_date=office_license_date,
                os_name=os_name,
                province=province,
                district=district,
                inspected_by_ict=inspected_by_ict,
                inspection_date=inspection_date,
                created_by_user_id=current_user().id if current_user() else None,
            )
            db.session.add(new_asset)
            db.session.commit()

            uploads_dir = Path(app.config['UPLOAD_FOLDER'])
            uploads_dir.mkdir(parents=True, exist_ok=True)

            if loss_file and loss_file.filename:
                ts = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
                safe_name = secure_filename(loss_file.filename)
                stored = f"{new_asset.id}_{ts}_{safe_name}" if safe_name else f"{new_asset.id}_{ts}"
                loss_file.save(str(uploads_dir / stored))
                doc_entry = AssetDocument(
                    asset_id=new_asset.id,
                    actor_user_id=current_user().id if current_user() else None,
                    doc_type='loss_evidence',
                    original_filename=loss_file.filename,
                    stored_filename=stored,
                )
                db.session.add(doc_entry)
                log_asset_activity(new_asset.id, 'upload_document', field='loss_evidence', old_value='', new_value=loss_file.filename)

            if specification_file and specification_file.filename:
                ts = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
                safe_name = secure_filename(specification_file.filename)
                stored = f"{new_asset.id}_{ts}_{safe_name}" if safe_name else f"{new_asset.id}_{ts}"
                specification_file.save(str(uploads_dir / stored))
                spec_entry = AssetDocument(
                    asset_id=new_asset.id,
                    actor_user_id=current_user().id if current_user() else None,
                    doc_type='specification',
                    original_filename=specification_file.filename,
                    stored_filename=stored,
                )
                db.session.add(spec_entry)
                log_asset_activity(new_asset.id, 'upload_document', field='specification', old_value='', new_value=specification_file.filename)

            if is_it() and inspection_file and inspection_file.filename:
                ts = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
                safe_name = secure_filename(inspection_file.filename)
                stored = f"{new_asset.id}_{ts}_{safe_name}" if safe_name else f"{new_asset.id}_{ts}"
                inspection_file.save(str(uploads_dir / stored))
                doc_entry = AssetDocument(
                    asset_id=new_asset.id,
                    actor_user_id=current_user().id if current_user() else None,
                    doc_type='inspection',
                    original_filename=inspection_file.filename,
                    stored_filename=stored,
                )
                db.session.add(doc_entry)
                log_asset_activity(new_asset.id, 'upload_document', field='inspection', old_value='', new_value=inspection_file.filename)

            db.session.commit()
            log_action('add_asset', 'Asset', new_asset.id, new_asset.name)
            log_asset_activity(new_asset.id, 'create')
            flash('Asset added successfully!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            log_action('add_asset_error', 'Asset', None, str(e))
            flash(f'Error adding asset: {e}', 'danger')
    
    return render_template('add_asset.html')

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_asset(id):
    asset = Asset.query.get_or_404(id)
    if not has_asset_edit_rights():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    q = filter_by_user_location(Asset.query.filter(Asset.id == id))
    if not q.first():
        flash('Access denied for this asset', 'danger')
        return redirect(url_for('index'))
    existing_loss_doc = AssetDocument.query.filter_by(asset_id=asset.id, doc_type='loss_evidence').order_by(AssetDocument.timestamp.desc()).first()
    if request.method == 'POST':
        current_status = (asset.status or '').strip()
        if current_status == 'Lost':
            current_status = 'Lost / Stolen'

        u = current_user()

        posted_status = (request.form.get('status') or '').strip() or current_status
        if posted_status == 'Lost':
            posted_status = 'Lost / Stolen'
        if posted_status not in ALLOWED_ASSET_STATUSES:
            flash('Invalid status selected', 'danger')
            return render_template('edit_asset.html', asset=asset, existing_loss_doc=existing_loss_doc)

        if current_status in LOCKED_ASSET_STATUSES:
            if not (current_status == 'Archived' and posted_status == 'Auctioned'):
                flash('Archived or Auctioned assets cannot be reactivated', 'danger')
                return redirect(url_for('view_asset', id=asset.id))

        attempted_relocate = False
        posted_province = (request.form.get('province') or '').strip()
        posted_district = (request.form.get('district') or '').strip()
        if u and u.role != 'IT' and u.province and u.province != 'Head Office':
            posted_province = u.province
        if u and u.role == 'AdminDistrict' and u.district:
            if posted_district and posted_district != u.district:
                attempted_relocate = True
            posted_district = u.district

        posted_assigned_to = (request.form.get('assigned_to') or '').strip()
        posted_assigned_to = posted_assigned_to or None
        repair_note = (request.form.get('repair_note') or '').strip()
        recovery_note = (request.form.get('recovery_note') or '').strip()

        posted_os = (request.form.get('os_name') or '').strip() or None
        posted_antivirus = (request.form.get('antivirus_name') or '').strip() or None
        posted_antivirus_license_date_str = (request.form.get('antivirus_license_date') or '').strip()
        posted_office = (request.form.get('office_name') or '').strip() or None
        posted_office_license_date_str = (request.form.get('office_license_date') or '').strip()

        posted_inspected = request.form.get('inspected_by_ict') == 'on'
        posted_inspection_date_str = (request.form.get('inspection_date') or '').strip()

        loss_file = request.files.get('loss_evidence')
        inspection_file = request.files.get('inspection_document')
        if posted_status == 'Lost / Stolen' and current_status != 'Lost / Stolen':
            if not loss_file and not existing_loss_doc:
                flash('Police report / evidence document is required for Lost / Stolen assets', 'danger')
                return render_template('edit_asset.html', asset=asset, existing_loss_doc=existing_loss_doc)
        if current_status == 'Lost / Stolen' and posted_status != 'Lost / Stolen':
            if not recovery_note:
                flash('Recovery notes are required when recovering a Lost / Stolen asset', 'danger')
                return render_template('edit_asset.html', asset=asset, existing_loss_doc=existing_loss_doc)
        if current_status == 'Broken' and posted_status in ['In Stock', 'In Use'] and posted_status != current_status:
            if not repair_note:
                flash('Repair notes are required when marking a Broken asset as Repaired', 'danger')
                return render_template('edit_asset.html', asset=asset, existing_loss_doc=existing_loss_doc)
        if posted_status == 'In Use' and not posted_assigned_to:
            flash('Assigned To is required when status is In Use', 'danger')
            return render_template('edit_asset.html', asset=asset, existing_loss_doc=existing_loss_doc)
        if posted_status != 'In Use' and posted_assigned_to:
            posted_assigned_to = None
            flash('Assigned To was cleared because the asset is not In Use', 'warning')

        immutable_attempted = False
        if (request.form.get('name') or '').strip() and (request.form.get('name') or '').strip() != (asset.name or ''):
            immutable_attempted = True
        if (request.form.get('serial_number') or '').strip() and (request.form.get('serial_number') or '').strip() != (asset.serial_number or ''):
            immutable_attempted = True
        if (request.form.get('supplier') or '').strip() and (request.form.get('supplier') or '').strip() != (asset.supplier or ''):
            immutable_attempted = True
        if (request.form.get('purchase_date') or '').strip():
            try:
                pd = datetime.strptime((request.form.get('purchase_date') or '').strip(), '%Y-%m-%d').date()
                if asset.purchase_date and pd != asset.purchase_date:
                    immutable_attempted = True
            except Exception:
                immutable_attempted = True
        if (request.form.get('type') or '').strip() and (request.form.get('type') or '').strip() != (asset.type or ''):
            immutable_attempted = True
        if immutable_attempted:
            flash('Some fields are immutable and were not changed', 'warning')

        old_values = {
            'province': asset.province,
            'district': asset.district,
            'assigned_to': asset.assigned_to,
            'status': asset.status,
            'os_name': asset.os_name,
            'antivirus_name': asset.antivirus_name,
            'antivirus_license_date': asset.antivirus_license_date.isoformat() if asset.antivirus_license_date else None,
            'office_name': asset.office_name,
            'office_license_date': asset.office_license_date.isoformat() if asset.office_license_date else None,
            'inspected_by_ict': 'Yes' if asset.inspected_by_ict else 'No',
            'inspection_date': asset.inspection_date.isoformat() if asset.inspection_date else None,
        }

        try:
            posted_antivirus_license_date = datetime.strptime(posted_antivirus_license_date_str, '%Y-%m-%d').date() if posted_antivirus_license_date_str else None
            posted_office_license_date = datetime.strptime(posted_office_license_date_str, '%Y-%m-%d').date() if posted_office_license_date_str else None

            asset.province = posted_province or None
            asset.district = posted_district or None
            asset.assigned_to = posted_assigned_to
            asset.status = posted_status
            if is_it():
                asset.os_name = posted_os
                asset.antivirus_name = posted_antivirus
                asset.antivirus_license_date = posted_antivirus_license_date
            asset.office_name = posted_office
            asset.office_license_date = posted_office_license_date

            uploads_dir = Path(app.config['UPLOAD_FOLDER'])
            uploads_dir.mkdir(parents=True, exist_ok=True)

            if not asset.inspected_by_ict and not asset.inspection_date:
                if is_it() and posted_inspected:
                    if not inspection_file or not inspection_file.filename:
                        flash('Inspection document is required when marking inspected', 'danger')
                        return render_template('edit_asset.html', asset=asset, existing_loss_doc=existing_loss_doc)
                    if not posted_inspection_date_str:
                        flash('Inspection date is required when marking inspected', 'danger')
                        return render_template('edit_asset.html', asset=asset, existing_loss_doc=existing_loss_doc)
                    asset.inspected_by_ict = True
                    asset.inspection_date = datetime.strptime(posted_inspection_date_str, '%Y-%m-%d').date()
                    ts = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
                    safe_name = secure_filename(inspection_file.filename)
                    stored = f"{asset.id}_{ts}_{safe_name}" if safe_name else f"{asset.id}_{ts}"
                    inspection_file.save(str(uploads_dir / stored))
                    doc_entry = AssetDocument(
                        asset_id=asset.id,
                        actor_user_id=current_user().id if current_user() else None,
                        doc_type='inspection',
                        original_filename=inspection_file.filename,
                        stored_filename=stored,
                    )
                    db.session.add(doc_entry)
                    log_asset_activity(asset.id, 'upload_document', field='inspection', old_value='', new_value=inspection_file.filename)

            if loss_file and loss_file.filename:
                ts = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
                safe_name = secure_filename(loss_file.filename)
                stored = f"{asset.id}_{ts}_{safe_name}" if safe_name else f"{asset.id}_{ts}"
                loss_file.save(str(uploads_dir / stored))
                doc_entry = AssetDocument(
                    asset_id=asset.id,
                    actor_user_id=current_user().id if current_user() else None,
                    doc_type='loss_evidence',
                    original_filename=loss_file.filename,
                    stored_filename=stored,
                )
                db.session.add(doc_entry)
                log_asset_activity(asset.id, 'upload_document', field='loss_evidence', old_value='', new_value=loss_file.filename)

            changes = []
            def add_change(action, field, old_val, new_val):
                if (old_val or '') != (new_val or ''):
                    changes.append(AssetActivity(
                        asset_id=asset.id,
                        actor_user_id=current_user().id if current_user() else None,
                        action=action,
                        field=field,
                        old_value=old_val,
                        new_value=new_val
                    ))

            add_change('update', 'province', old_values['province'] or '', asset.province or '')
            add_change('update', 'district', old_values['district'] or '', asset.district or '')
            add_change('update', 'assigned_to', old_values['assigned_to'] or '', asset.assigned_to or '')
            add_change('status', 'status', (current_status or ''), asset.status or '')
            add_change('software', 'os_name', old_values['os_name'] or '', asset.os_name or '')
            add_change('software', 'antivirus_name', old_values['antivirus_name'] or '', asset.antivirus_name or '')
            add_change('software', 'antivirus_license_date', old_values['antivirus_license_date'] or '', asset.antivirus_license_date.isoformat() if asset.antivirus_license_date else '')
            add_change('software', 'office_name', old_values['office_name'] or '', asset.office_name or '')
            add_change('software', 'office_license_date', old_values['office_license_date'] or '', asset.office_license_date.isoformat() if asset.office_license_date else '')
            add_change('inspection', 'inspected_by_ict', old_values['inspected_by_ict'] or '', 'Yes' if asset.inspected_by_ict else 'No')
            add_change('inspection', 'inspection_date', old_values['inspection_date'] or '', asset.inspection_date.isoformat() if asset.inspection_date else '')
            if current_status == 'Broken' and posted_status in ['In Stock', 'In Use'] and posted_status != current_status and repair_note:
                changes.append(AssetActivity(
                    asset_id=asset.id,
                    actor_user_id=current_user().id if current_user() else None,
                    action='repair',
                    field='note',
                    old_value='',
                    new_value=repair_note
                ))
            if current_status == 'Lost / Stolen' and posted_status != 'Lost / Stolen' and recovery_note:
                changes.append(AssetActivity(
                    asset_id=asset.id,
                    actor_user_id=current_user().id if current_user() else None,
                    action='recover',
                    field='note',
                    old_value='',
                    new_value=recovery_note
                ))

            if changes:
                db.session.add_all(changes)

            db.session.commit()
            log_action('edit_asset', 'Asset', asset.id, asset.name)
            if attempted_relocate:
                flash('You have no right to relocate an asset to another district', 'warning')
            flash('Asset updated successfully!', 'success')
            return redirect(url_for('view_asset', id=asset.id))
        except Exception as e:
            db.session.rollback()
            log_action('edit_asset_error', 'Asset', asset.id, str(e))
            flash(f'Error updating asset: {e}', 'danger')

    return render_template('edit_asset.html', asset=asset, existing_loss_doc=existing_loss_doc)

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_asset(id):
    asset = Asset.query.get_or_404(id)
    if not has_asset_edit_rights():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    if current_user() and current_user().role == 'AdminDistrict':
        flash('You have no right to delete assets', 'danger')
        return redirect(url_for('index'))
    q = filter_by_user_location(Asset.query.filter(Asset.id == id))
    if not q.first():
        flash('Access denied for this asset', 'danger')
        return redirect(url_for('index'))
    try:
        if (asset.status or '').strip() in LOCKED_ASSET_STATUSES and (asset.status or '').strip() == 'Archived':
            flash('Asset is already archived', 'info')
            return redirect(url_for('view_asset', id=asset.id))
        old_status = asset.status or ''
        old_assigned = asset.assigned_to or ''
        asset.status = 'Archived'
        asset.assigned_to = None
        activities = [
            AssetActivity(
                asset_id=asset.id,
                actor_user_id=current_user().id if current_user() else None,
                action='archive',
                field='status',
                old_value=old_status,
                new_value='Archived'
            )
        ]
        if old_assigned:
            activities.append(AssetActivity(
                asset_id=asset.id,
                actor_user_id=current_user().id if current_user() else None,
                action='archive',
                field='assigned_to',
                old_value=old_assigned,
                new_value=''
            ))
        db.session.add_all(activities)
        db.session.commit()
        log_action('archive_asset', 'Asset', id, asset.name)
        flash('Asset archived successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        log_action('archive_asset_error', 'Asset', id, str(e))
        flash(f'Error archiving asset: {e}', 'danger')
    return redirect(url_for('index'))

@app.route('/assets/<int:asset_id>/documents/<int:doc_id>/download', methods=['GET'])
@login_required
def download_asset_document(asset_id, doc_id):
    doc = AssetDocument.query.get_or_404(doc_id)
    if doc.asset_id != asset_id:
        abort(404)
    q = filter_by_user_location(Asset.query.filter(Asset.id == asset_id))
    asset = q.first()
    if not asset:
        flash('Access denied for this asset', 'danger')
        return redirect(url_for('index'))
    uploads_dir = Path(app.config['UPLOAD_FOLDER'])
    return send_from_directory(
        directory=str(uploads_dir),
        path=doc.stored_filename,
        as_attachment=True,
        download_name=doc.original_filename
    )

@app.route('/view/<int:id>', methods=['GET'])
@login_required
def view_asset(id):
    asset = Asset.query.get_or_404(id)
    q = filter_by_user_location(Asset.query.filter(Asset.id == id))
    if not q.first():
        flash('Access denied for this asset', 'danger')
        return redirect(url_for('index'))
    log_action('view_asset', 'Asset', id, asset.name)
    activities = AssetActivity.query.filter_by(asset_id=asset.id).order_by(AssetActivity.timestamp.desc()).all()
    docs = AssetDocument.query.filter_by(asset_id=asset.id).order_by(AssetDocument.timestamp.desc()).all()
    actor_ids = sorted({a.actor_user_id for a in activities if a.actor_user_id})
    actor_map = {}
    if actor_ids:
        for u in User.query.filter(User.id.in_(actor_ids)).all():
            actor_map[u.id] = u.username
    return render_template('view_asset.html', asset=asset, activities=activities, docs=docs, actor_map=actor_map)

def get_report_assets(report_type):
    q = filter_by_user_location(Asset.query)
    # Base subsets by report_type
    if report_type == 'all':
        q = q.filter(~Asset.status.in_(LOCKED_ASSET_STATUSES))
    elif report_type == 'computers_health':
        q = q.filter(Asset.type.in_(['Laptop', 'Desktop', 'All-in-One']))
    elif report_type == 'approaching_eol':
        # handle via post-filtering because computed property
        pass
    elif report_type == 'past_eol':
        pass
    elif report_type == 'inspections':
        q = q.filter(Asset.inspected_by_ict == True)
    elif report_type == 'uninspected':
        q = q.filter((Asset.inspected_by_ict == False) | (Asset.inspected_by_ict.is_(None)))
    elif report_type == 'archived_auctioned':
        q = q.filter(Asset.status.in_(LOCKED_ASSET_STATUSES))
    elif report_type == 'donated':
        q = q.filter(Asset.acquisition_type == 'Donated')
    elif report_type == 'purchased':
        q = q.filter(Asset.acquisition_type == 'Purchased')

    # Optional filters via query params
    name = request.args.get('assigned_to') or ''
    supplier = request.args.get('supplier') or ''
    province = request.args.get('province') or ''
    district = request.args.get('district') or ''
    uninspected_only = request.args.get('uninspected') == 'on'
    status = request.args.get('status') or ''
    start_date_str = (request.args.get('start_date') or '').strip()
    end_date_str = (request.args.get('end_date') or '').strip()

    if name.strip():
        q = q.filter(Asset.assigned_to == name.strip())
    if supplier.strip():
        q = q.filter(Asset.supplier == supplier.strip())
    if status.strip():
        q = q.filter(Asset.status == status.strip())
    if province.strip():
        q = q.filter(Asset.province == province.strip())
        if province.strip() != 'Head Office' and district.strip():
            q = q.filter(Asset.district == district.strip())
    elif district.strip():
        q = q.filter(Asset.district == district.strip())
    if uninspected_only:
        q = q.filter((Asset.inspected_by_ict == False) | (Asset.inspected_by_ict.is_(None)))
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            q = q.filter(Asset.purchase_date >= start_date)
        except Exception:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            q = q.filter(Asset.purchase_date <= end_date)
        except Exception:
            pass

    assets = q.all()
    if report_type == 'approaching_eol':
        assets = [a for a in assets if a.is_eol_approaching]
    if report_type == 'past_eol':
        assets = [a for a in assets if a.is_eol_passed]
    return assets

def asset_rows(assets):
    rows = []
    for a in assets:
        rows.append({
            'ID': a.id,
            'Name': a.name,
            'Type': a.type,
            'Serial': a.serial_number,
            'Purchase Date': a.purchase_date.isoformat() if a.purchase_date else '',
            'Acquisition Type': a.acquisition_type or '',
            'Status': a.status,
            'Assigned To': a.assigned_to or '',
            'Supplier': a.supplier or '',
            'Donor Name': a.donor_name or '',
            'Province': a.province or '',
            'District': a.district or '',
            'OS': a.os_name or '',
            'Antivirus': a.antivirus_name or '',
            'Antivirus License': a.antivirus_license_date.isoformat() if a.antivirus_license_date else '',
            'Office': a.office_name or '',
            'Office License': a.office_license_date.isoformat() if a.office_license_date else '',
            'EOL Date': a.eol_date.isoformat() if a.eol_date else '',
            'EOL Status': a.eol_status or '',
            'Inspected': 'Yes' if a.inspected_by_ict else 'No',
            'Inspection Date': a.inspection_date.isoformat() if a.inspection_date else '',
        })
    return rows

@app.route('/reports')
@login_required
def reports():
    report_type = request.args.get('type', 'all')
    assets = []
    movements = []
    status_counts = None
    if report_type != 'movement':
        assets = get_report_assets(report_type)
        status_counts = {s: 0 for s in ALLOWED_ASSET_STATUSES}
        for a in assets:
            s = (a.status or '').strip()
            if s in status_counts:
                status_counts[s] += 1
    suppliers = [
        r[0] for r in filter_by_user_location(Asset.query)
        .with_entities(Asset.supplier)
        .filter(Asset.supplier.isnot(None))
        .filter(Asset.supplier != '')
        .distinct()
        .order_by(Asset.supplier)
        .all()
        if r[0]
    ]
    if report_type == 'movement':
        q = db.session.query(AssetActivity, Asset).join(Asset, Asset.id == AssetActivity.asset_id)
        q = filter_by_user_location(q)
        q = q.filter(AssetActivity.field.in_(['province', 'district', 'assigned_to', 'status']))
        asset_id_str = (request.args.get('asset_id') or '').strip()
        serial = (request.args.get('serial') or '').strip()
        movement_field = (request.args.get('movement_field') or '').strip()
        start_date_str = (request.args.get('start_date') or '').strip()
        end_date_str = (request.args.get('end_date') or '').strip()
        if asset_id_str:
            try:
                asset_id_val = int(asset_id_str)
                q = q.filter(Asset.id == asset_id_val)
            except Exception:
                pass
        if serial:
            q = q.filter(Asset.serial_number == serial)
        if movement_field:
            q = q.filter(AssetActivity.field == movement_field)
        if start_date_str:
            try:
                start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
                q = q.filter(AssetActivity.timestamp >= start_dt)
            except Exception:
                pass
        if end_date_str:
            try:
                end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
                q = q.filter(AssetActivity.timestamp <= end_dt)
            except Exception:
                pass
        q = q.order_by(AssetActivity.timestamp.desc()).limit(500)
        rows = q.all()
        actor_ids = sorted({a.actor_user_id for (a, _) in rows if a.actor_user_id})
        actor_map = {}
        if actor_ids:
            for u in User.query.filter(User.id.in_(actor_ids)).all():
                actor_map[u.id] = u.username
        movements = []
        for a, asset in rows:
            old_val = a.old_value or ''
            new_val = a.new_value or ''
            desc = ''
            if a.field == 'status':
                if old_val and new_val:
                    desc = f"Status changed from {old_val} to {new_val}"
                elif new_val:
                    desc = f"Status set to {new_val}"
            elif a.field == 'assigned_to':
                if not new_val and old_val:
                    if a.action == 'archive':
                        desc = f"Assignment cleared from {old_val} when asset was archived"
                    else:
                        desc = f"Assignment cleared from {old_val}"
                elif old_val and new_val:
                    desc = f"Assigned to changed from {old_val} to {new_val}"
                elif new_val:
                    desc = f"Assigned to set to {new_val}"
            elif a.field == 'province':
                if old_val and new_val:
                    desc = f"Province changed from {old_val} to {new_val}"
                elif new_val:
                    desc = f"Province set to {new_val}"
            elif a.field == 'district':
                if old_val and new_val:
                    desc = f"District changed from {old_val} to {new_val}"
                elif new_val:
                    desc = f"District set to {new_val}"
            if not desc:
                if old_val or new_val:
                    desc = f"{a.field} changed from {old_val or '-'} to {new_val or '-'}"
                else:
                    desc = f"{a.field} changed"
            movements.append(
                {
                    'timestamp': a.timestamp,
                    'asset_id': asset.id,
                    'name': asset.name,
                    'serial': asset.serial_number,
                    'province': asset.province,
                    'district': asset.district,
                    'action': a.action,
                    'field': a.field,
                    'old_value': a.old_value,
                    'new_value': a.new_value,
                    'user': actor_map.get(a.actor_user_id, 'System') if a.actor_user_id else 'System',
                    'description': desc,
                }
            )
    log_action('view_reports', details=report_type)
    return render_template(
        'reports.html',
        assets=assets,
        report_type=report_type,
        suppliers=suppliers,
        movements=movements,
        status_counts=status_counts,
    )

@app.route('/export/<fmt>')
@login_required
def export(fmt):
    report_type = request.args.get('type', 'all')
    rows = []
    assets = []
    filename_base = ''
    if report_type == 'movement':
        q = db.session.query(AssetActivity, Asset).join(Asset, Asset.id == AssetActivity.asset_id)
        q = filter_by_user_location(q)
        q = q.filter(AssetActivity.field.in_(['province', 'district', 'assigned_to', 'status']))
        asset_id_str = (request.args.get('asset_id') or '').strip()
        serial = (request.args.get('serial') or '').strip()
        movement_field = (request.args.get('movement_field') or '').strip()
        start_date_str = (request.args.get('start_date') or '').strip()
        end_date_str = (request.args.get('end_date') or '').strip()
        if asset_id_str:
            try:
                asset_id_val = int(asset_id_str)
                q = q.filter(Asset.id == asset_id_val)
            except Exception:
                pass
        if serial:
            q = q.filter(Asset.serial_number == serial)
        if movement_field:
            q = q.filter(AssetActivity.field == movement_field)
        if start_date_str:
            try:
                start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
                q = q.filter(AssetActivity.timestamp >= start_dt)
            except Exception:
                pass
        if end_date_str:
            try:
                end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
                q = q.filter(AssetActivity.timestamp <= end_dt)
            except Exception:
                pass
        q = q.order_by(AssetActivity.timestamp.desc()).limit(500)
        db_rows = q.all()
        actor_ids = sorted({a.actor_user_id for (a, _) in db_rows if a.actor_user_id})
        actor_map = {}
        if actor_ids:
            for u in User.query.filter(User.id.in_(actor_ids)).all():
                actor_map[u.id] = u.username
        for a, asset in db_rows:
            old_val = a.old_value or ''
            new_val = a.new_value or ''
            desc = ''
            if a.field == 'status':
                if old_val and new_val:
                    desc = f"Status changed from {old_val} to {new_val}"
                elif new_val:
                    desc = f"Status set to {new_val}"
            elif a.field == 'assigned_to':
                if not new_val and old_val:
                    if a.action == 'archive':
                        desc = f"Assignment cleared from {old_val} when asset was archived"
                    else:
                        desc = f"Assignment cleared from {old_val}"
                elif old_val and new_val:
                    desc = f"Assigned to changed from {old_val} to {new_val}"
                elif new_val:
                    desc = f"Assigned to set to {new_val}"
            elif a.field == 'province':
                if old_val and new_val:
                    desc = f"Province changed from {old_val} to {new_val}"
                elif new_val:
                    desc = f"Province set to {new_val}"
            elif a.field == 'district':
                if old_val and new_val:
                    desc = f"District changed from {old_val} to {new_val}"
                elif new_val:
                    desc = f"District set to {new_val}"
            if not desc:
                if old_val or new_val:
                    desc = f"{a.field} changed from {old_val or '-'} to {new_val or '-'}"
                else:
                    desc = f"{a.field} changed"
            rows.append({
                'Date / Time': a.timestamp.isoformat() if a.timestamp else '',
                'Asset ID': asset.id,
                'Name': asset.name,
                'Serial': asset.serial_number,
                'Province': asset.province or '',
                'District': asset.district or '',
                'Action': a.action,
                'Field': a.field,
                'Old Value': a.old_value or '',
                'New Value': a.new_value or '',
                'User': actor_map.get(a.actor_user_id, 'System') if a.actor_user_id else 'System',
                'Description': desc,
            })
        filename_base = f"movement_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    else:
        assets = get_report_assets(report_type)
        rows = asset_rows(assets)
        filename_base = f"report_{report_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if fmt == 'csv' or fmt == 'excel':
        si = io.StringIO()
        writer = csv.DictWriter(si, fieldnames=list(rows[0].keys()) if rows else [
            'ID','Name','Type','Serial','Purchase Date','Status','Assigned To','Supplier','Province','District','OS','Antivirus','Antivirus License','Office','Office License','EOL Date','EOL Status','Inspected','Inspection Date'
        ])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        output = si.getvalue()
        content_type = 'text/csv' if fmt == 'csv' else 'application/vnd.ms-excel'
        return Response(
            output,
            mimetype=content_type,
            headers={'Content-Disposition': f'attachment; filename="{filename_base}.csv"'}
        )
    if fmt == 'word':
        html = "<html><body><h2>ICT Asset Report</h2><table border='1' cellspacing='0' cellpadding='4'>"
        # header
        headers = list(rows[0].keys()) if rows else []
        if headers:
            html += "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
        for r in rows:
            html += "<tr>" + "".join(f"<td>{(r.get(h) or '')}</td>" for h in headers) + "</tr>"
        html += "</table></body></html>"
        return Response(
            html,
            mimetype='application/msword',
            headers={'Content-Disposition': f'attachment; filename="{filename_base}.doc"'}
        )
    if fmt == 'pdf':
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import cm
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=A4)
            width, height = A4
            y = height - 2*cm
            c.setFont("Helvetica-Bold", 14)
            c.drawString(2*cm, y, "ICT Asset Report")
            y -= 1*cm
            c.setFont("Helvetica", 9)
            for r in rows or []:
                line = f"{r['ID']} | {r['Name']} | {r['Type']} | {r['Serial']} | {r['Status']} | {r.get('Supplier','')} | {r['Province']} | {r['District']} | EOL: {r['EOL Date']} {r['EOL Status']} | Inspected: {r['Inspected']}"
                c.drawString(2*cm, y, line[:200])
                y -= 0.6*cm
                if y < 2*cm:
                    c.showPage()
                    y = height - 2*cm
                    c.setFont("Helvetica", 9)
            c.save()
            pdf = buf.getvalue()
            buf.close()
            return Response(
                pdf,
                mimetype='application/pdf',
                headers={'Content-Disposition': f'attachment; filename="{filename_base}.pdf"'}
            )
        except Exception:
            printable = render_template('reports_print.html', assets=assets, report_type=report_type)
            return Response(
                printable,
                mimetype='text/html'
            )
    log_action('export_report', details=f'{fmt}:{report_type}')
    return redirect(url_for('reports', type=report_type))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        if len(password) < 8:
            flash('Password must be at least 8 characters', 'danger')
            return render_template('login.html')
        user = User.query.filter_by(username=username).first()
        if user and user.active and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session.permanent = True
            log_action('login_success')
            return redirect(url_for('index'))
        log_action('login_failed', details=username)
        flash('Invalid credentials or inactive user', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    log_action('logout')
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    u = current_user()
    if not u:
        return redirect(url_for('login'))
    if request.method == 'POST':
        current_pw = (request.form.get('current_password') or '').strip()
        new_pw = (request.form.get('new_password') or '').strip()
        confirm_pw = (request.form.get('confirm_password') or '').strip()
        if not current_pw or not new_pw or not confirm_pw:
            flash('All password fields are required', 'danger')
            return render_template('change_password.html')
        if not check_password_hash(u.password_hash, current_pw):
            flash('Current password is incorrect', 'danger')
            return render_template('change_password.html')
        if len(new_pw) < 8:
            flash('New password must be at least 8 characters', 'danger')
            return render_template('change_password.html')
        if new_pw != confirm_pw:
            flash('New password and confirmation do not match', 'danger')
            return render_template('change_password.html')
        u.password_hash = generate_password_hash(new_pw)
        db.session.commit()
        log_action('password_changed_self', 'User', u.id)
        flash('Password updated successfully', 'success')
        return redirect(url_for('index'))
    return render_template('change_password.html')

@app.route('/users', methods=['GET', 'POST'])
@login_required
def users():
    if not is_it():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        role = (request.form.get('role') or '').strip()
        province = (request.form.get('province') or '').strip()
        district = (request.form.get('district') or '').strip()
        email = (request.form.get('email') or '').strip()
        if len(password) < 8:
            flash('Password must be at least 8 characters', 'danger')
            return redirect(url_for('users'))
        if not username or not password or role not in ['IT', 'Admin', 'AdminProvince', 'AdminDistrict', 'Viewer']:
            flash('Invalid user data', 'danger')
            return redirect(url_for('users'))
        # Enforce location requirements by role
        if role == 'AdminProvince':
            if not province:
                flash('Province is required for Admin (Province) users', 'danger')
                return redirect(url_for('users'))
            # assign all districts for the province as a comma-separated list
            districts = PROVINCE_DISTRICTS.get(province, [])
            district = ", ".join(districts) if districts else ''
        if role == 'AdminDistrict':
            if not province or province == 'Head Office':
                flash('Valid province is required for Admin (District) users', 'danger')
                return redirect(url_for('users'))
            if not district:
                flash('District is required for Admin (District) users', 'danger')
                return redirect(url_for('users'))
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('users'))
        u = User(
            username=username,
            password_hash=generate_password_hash(password),
            role=role,
            province=(province or None),
            district=(district or None),
            email=email or None
        )
        db.session.add(u)
        db.session.commit()
        log_action('create_user', 'User', u.id, u.username)
        flash('User created', 'success')
        return redirect(url_for('users'))
    all_users = User.query.all()
    return render_template('users.html', users=all_users)

class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    token = db.Column(db.String(120), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)

def ensure_schema():
    with app.app_context():
        db.create_all()
        cols = [r[1] for r in db.session.execute(text("PRAGMA table_info(asset)")).fetchall()]
        if 'supplier' not in cols:
            db.session.execute(text("ALTER TABLE asset ADD COLUMN supplier VARCHAR(120)"))
            db.session.commit()
        if 'acquisition_type' not in cols:
            db.session.execute(text("ALTER TABLE asset ADD COLUMN acquisition_type VARCHAR(20)"))
            db.session.commit()
        if 'donor_name' not in cols:
            db.session.execute(text("ALTER TABLE asset ADD COLUMN donor_name VARCHAR(120)"))
            db.session.commit()
        if 'capture_date' not in cols:
            db.session.execute(text("ALTER TABLE asset ADD COLUMN capture_date DATE"))
            db.session.commit()

ensure_schema()

def generate_reset_token(user_id):
    import secrets
    token = secrets.token_urlsafe(32)
    pr = PasswordResetToken(
        user_id=user_id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(hours=2),
        used=False
    )
    db.session.add(pr)
    db.session.commit()
    return token

@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip()
        user = None
        if username:
            user = User.query.filter_by(username=username).first()
        elif email:
            user = User.query.filter_by(email=email).first()
        if not user:
            flash('User not found', 'danger')
            return render_template('forgot.html')
        token = generate_reset_token(user.id)
        link = url_for('reset_password', token=token, _external=True)
        sent = False
        if user.email:
            sent = send_email(user.email, 'Password Reset', f'Click to reset your password: <a href="{link}">{link}</a>')
        log_action('password_reset_requested', 'User', user.id, 'email_sent' if sent else 'email_failed')
        if sent:
            flash('Password reset email sent', 'success')
        else:
            flash(f'Password reset link: {link}', 'info')
        return redirect(url_for('login'))
    return render_template('forgot.html')

@app.route('/users/<int:id>/reset', methods=['POST'])
@login_required
def admin_reset_user(id):
    if not is_it():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    token = generate_reset_token(user.id)
    link = url_for('reset_password', token=token, _external=True)
    sent = False
    if user.email:
        sent = send_email(user.email, 'Password Reset', f'Click to reset your password: <a href="{link}">{link}</a>')
    log_action('password_reset_admin_requested', 'User', user.id, 'email_sent' if sent else 'email_failed')
    if sent:
        flash('Password reset email sent', 'success')
    else:
        flash(f'Password reset link: {link}', 'info')
    return redirect(url_for('users'))

@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    pr = PasswordResetToken.query.filter_by(token=token, used=False).first()
    if not pr or pr.expires_at < datetime.utcnow():
        flash('Invalid or expired token', 'danger')
        return redirect(url_for('login'))
    user = User.query.get(pr.user_id)
    if request.method == 'POST':
        password = (request.form.get('password') or '').strip()
        if not password:
            flash('Password required', 'danger')
            return render_template('reset.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters', 'danger')
            return render_template('reset.html')
        user.password_hash = generate_password_hash(password)
        pr.used = True
        db.session.commit()
        log_action('password_reset_completed', 'User', user.id)
        flash('Password updated', 'success')
        return redirect(url_for('login'))
    return render_template('reset.html')

@app.route('/audit')
@login_required
def audit():
    if not is_it():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    action = request.args.get('action') or ''
    actor = request.args.get('actor') or ''
    q = AuditLog.query.order_by(AuditLog.timestamp.desc())
    if action:
        q = q.filter(AuditLog.action == action)
    if actor:
        try:
            actor_id = int(actor)
            q = q.filter(AuditLog.actor_user_id == actor_id)
        except Exception:
            pass
    logs = q.all()
    backup_dir = Path("D:/ICTAssetBackups")
    backup_files = []
    try:
        if backup_dir.exists():
            files = sorted(backup_dir.glob("inventory_backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
            for f in files[:20]:
                st = f.stat()
                backup_files.append({
                    'name': f.name,
                    'size': st.st_size,
                    'mtime': datetime.fromtimestamp(st.st_mtime)
                })
    except Exception:
        backup_files = []
    return render_template('audit.html', logs=logs, backup_files=backup_files, backup_dir=str(backup_dir))

@app.route('/backup/download')
@login_required
def download_backup():
    if not is_it():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    db_path = Path(app.instance_path) / 'inventory.db'
    if not db_path.exists():
        flash('Database file not found for backup', 'danger')
        return redirect(url_for('audit'))
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"inventory_backup_{ts}.db"
    return send_from_directory(
        directory=str(db_path.parent),
        path=db_path.name,
        as_attachment=True,
        download_name=filename
    )

@app.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    if not is_it():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        role = (request.form.get('role') or '').strip()
        province = (request.form.get('province') or '').strip()
        district = (request.form.get('district') or '').strip()
        password = (request.form.get('password') or '').strip()
        email = (request.form.get('email') or '').strip()
        if not username or role not in ['IT', 'Admin', 'AdminProvince', 'AdminDistrict', 'Viewer']:
            flash('Invalid user data', 'danger')
            return redirect(url_for('edit_user', id=id))
        existing = User.query.filter(User.username == username, User.id != id).first()
        if existing:
            flash('Username already exists', 'danger')
            return redirect(url_for('edit_user', id=id))
        user.username = username
        user.role = role
        # Enforce location requirements by role
        if role == 'AdminProvince':
            if not province:
                flash('Province is required for Admin (Province) users', 'danger')
                return redirect(url_for('edit_user', id=id))
            user.province = province
            # assign all districts for the province as a comma-separated list
            districts = PROVINCE_DISTRICTS.get(province, [])
            user.district = ", ".join(districts) if districts else None
        elif role == 'AdminDistrict':
            if not province or province == 'Head Office':
                flash('Valid province is required for Admin (District) users', 'danger')
                return redirect(url_for('edit_user', id=id))
            if not district:
                flash('District is required for Admin (District) users', 'danger')
                return redirect(url_for('edit_user', id=id))
            user.province = province
            user.district = district
        else:
            user.province = province or None
            user.district = district or None
        user.email = email or None
        if password:
            if len(password) < 8:
                flash('Password must be at least 8 characters', 'danger')
                return redirect(url_for('edit_user', id=id))
            user.password_hash = generate_password_hash(password)
        db.session.commit()
        log_action('update_user', 'User', user.id, user.username)
        flash('User updated', 'success')
        return redirect(url_for('users'))
    return render_template('edit_user.html', user=user)

@app.route('/users/<int:id>/toggle_active', methods=['POST'])
@login_required
def toggle_user_active(id):
    if not is_it():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    if current_user().id == user.id:
        flash('Cannot change active state of your own account', 'danger')
        return redirect(url_for('users'))
    user.active = not user.active
    db.session.commit()
    log_action('toggle_user_active', 'User', user.id, user.username)
    flash('User state updated', 'success')
    return redirect(url_for('users'))

@app.route('/users/<int:id>/delete', methods=['POST'])
@login_required
def delete_user(id):
    if not is_it():
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    user = User.query.get_or_404(id)
    if current_user().id == user.id:
        flash('Cannot delete your own account', 'danger')
        return redirect(url_for('users'))
    count_assets = Asset.query.filter_by(created_by_user_id=user.id).count()
    count_activities = AssetActivity.query.filter_by(actor_user_id=user.id).count()
    count_docs = AssetDocument.query.filter_by(actor_user_id=user.id).count()
    count_audit = AuditLog.query.filter_by(actor_user_id=user.id).count()
    if (count_assets + count_activities + count_docs + count_audit) > 0:
        log_action('delete_user_rejected', 'User', user.id, f'have_history assets={count_assets} activities={count_activities} docs={count_docs} audit={count_audit}')
        flash('Cannot delete user with historical activity. Deactivate the user instead.', 'danger')
        return redirect(url_for('users'))
    db.session.delete(user)
    db.session.commit()
    log_action('delete_user', 'User', user.id, user.username)
    flash('User deleted', 'success')
    return redirect(url_for('users'))
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if User.query.count() == 0:
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                role='IT',
                province='Head Office',
                district=None
            )
            db.session.add(admin)
            db.session.commit()
    import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
