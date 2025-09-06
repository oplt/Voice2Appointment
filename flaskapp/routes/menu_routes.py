from decimal import Decimal
from flask import Blueprint, request, redirect, url_for, flash
from flask_login import login_required, current_user
from flaskapp import db
from flaskapp.database.models import Category, Product, Menu, MenuItem

menu_bp = Blueprint('menu_bp', __name__, url_prefix='/menu')

DEFAULT_CATEGORIES = [
    ('snack', 'Snack'),
    ('spices', 'Spices'),
    ('cold_drink', 'Cold Drink'),
    ('hot_drink', 'Hot Drink'),
    ('hamburgers', 'Hamburgers'),
]

def ensure_default_categories():
    existing = {c.slug for c in Category.query.all()}
    order = 1
    for slug, name in DEFAULT_CATEGORIES:
        if slug not in existing:
            db.session.add(Category(slug=slug, name=name, sort_order=order))
        order += 1
    db.session.commit()

def _redirect_back(menu_id=None):
    return redirect(url_for('dashboard_bp.dashboard', tab='menu', menu_id=menu_id) if menu_id
                    else url_for('dashboard_bp.dashboard', tab='menu'))

@login_required
@menu_bp.route('/product/create', methods=['POST'])
def create_product():
    ensure_default_categories()
    name = (request.form.get('name') or '').strip()
    price = request.form.get('price') or '0'
    category_id = request.form.get('category_id', type=int)
    menu_id = request.form.get('menu_id', type=int)

    if not name:
        flash('Product name is required', 'warning')
        return _redirect_back(menu_id)

    # next sort order within category
    max_order = db.session.query(db.func.coalesce(db.func.max(Product.sort_order), 0)).filter_by(category_id=category_id).scalar() or 0

    prod = Product(
        category_id=category_id,
        name=name,
        price=Decimal(price),
        sort_order=max_order + 1,
    )
    db.session.add(prod)
    db.session.commit()
    flash('Product added', 'success')
    return _redirect_back(menu_id)

@login_required
@menu_bp.route('/product/<int:product_id>/delete', methods=['POST'])
def delete_product(product_id):
    menu_id = request.form.get('menu_id', type=int)
    p = Product.query.filter_by(id=product_id).first_or_404()
    db.session.delete(p)
    db.session.commit()
    flash('Product deleted', 'info')
    return _redirect_back(menu_id)

@login_required
@menu_bp.route('/product/<int:product_id>/move', methods=['POST'])
def move_product(product_id):
    menu_id = request.form.get('menu_id', type=int)
    new_cat_id = request.form.get('category_id', type=int)
    p = Product.query.filter_by(id=product_id).first_or_404()
    p.category_id = new_cat_id
    # put at end of target section
    max_order = db.session.query(db.func.coalesce(db.func.max(Product.sort_order), 0)).filter_by( category_id=new_cat_id
    ).scalar() or 0
    p.sort_order = max_order + 1
    db.session.commit()
    flash('Product moved', 'success')
    return _redirect_back(menu_id)

@login_required
@menu_bp.route('/product/<int:product_id>/reorder', methods=['POST'])
def reorder_product(product_id):
    menu_id = request.form.get('menu_id', type=int)
    direction = request.form.get('direction', 'up')
    p = Product.query.filter_by(id=product_id).first_or_404()
    sibling_q = Product.query.filter_by(category_id=p.category_id)
    if direction == 'up':
        neighbor = sibling_q.filter(Product.sort_order < p.sort_order).order_by(Product.sort_order.desc()).first()
    else:
        neighbor = sibling_q.filter(Product.sort_order > p.sort_order).order_by(Product.sort_order.asc()).first()
    if neighbor:
        p.sort_order, neighbor.sort_order = neighbor.sort_order, p.sort_order
        db.session.commit()
    return _redirect_back(menu_id)

@login_required
@menu_bp.route('/create', methods=['POST'])
def create_menu():
    ensure_default_categories()
    name = (request.form.get('name') or '').strip()
    if not name:
        flash('Menu name is required', 'warning')
        return _redirect_back()
    m = Menu(name=name)
    db.session.add(m)
    db.session.commit()
    flash('Menu created', 'success')
    return _redirect_back(m.id)

@login_required
@menu_bp.route('/<int:menu_id>/add', methods=['POST'])
def add_to_menu(menu_id):
    product_id = request.form.get('product_id', type=int)
    qty = request.form.get('quantity', type=int) or 1
    price_override = request.form.get('price_override')
    m = Menu.query.filter_by(id=menu_id).first_or_404()
    p = Product.query.filter_by(id=product_id).first_or_404()

    existing = MenuItem.query.filter_by(menu_id=m.id, product_id=p.id).first()
    if existing:
        existing.quantity += qty
    else:
        mi = MenuItem(menu_id=m.id, product_id=p.id, quantity=qty)
        if price_override:
            mi.price_override = Decimal(price_override)
        db.session.add(mi)

    db.session.commit()
    flash('Added to menu', 'success')
    return _redirect_back(m.id)

@login_required
@menu_bp.route('/<int:menu_id>/item/<int:item_id>/remove', methods=['POST'])
def remove_item(menu_id, item_id):
    m = Menu.query.filter_by(id=menu_id).first_or_404()
    it = MenuItem.query.filter_by(id=item_id, menu_id=m.id).first_or_404()
    db.session.delete(it)
    db.session.commit()
    flash('Removed from menu', 'info')
    return _redirect_back(m.id)
