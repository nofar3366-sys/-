"""CLI commands:
    flask --app app init-db          create tables / add new columns (keeps data)
    flask --app app seed             admin user + starter category and services (new database only)
    flask --app app seed-demo        demo projects with generated placeholder images
    flask --app app reset-password   set a new admin password
    flask --app app export           static site for Netlify -> dist/
"""
import io
import random

import click
from flask import current_app
from werkzeug.datastructures import FileStorage

from .extensions import db
from .models import Admin, Category, Project, ProjectImage, Service
from .validators import DEFAULT_ADMIN_PASSWORD, validate_new_password

STARTER_CATEGORIES = [("product-campaigns", "קמפייני מוצר", "Product Campaigns")]

STARTER_SERVICES = [  # DRAFT copy, edited from the admin
    ("קמפייני מוצר ב-AI", "AI Product Campaigns",
     "ויז'ואלים לקמפיין שלם סביב המוצר שלכם, בלי צורך בהפקת צילום.",
     "Full campaign imagery around your product, without a photo shoot."),
    ("תוכן ויזואלי למותגים", "Brand Visual Content",
     "סדרות תמונות בשפה אחידה לאתר, לקטלוג ולחומרי מכירה.",
     "Consistent image series for your website, catalogue and sales materials."),
    ("ויז'ואלים לרשתות חברתיות", "Social Media Visuals",
     "תוכן שמותאם לאינסטגרם ולטיקטוק, בפורמטים הנכונים.",
     "Content tailored to Instagram and TikTok, in the right formats."),
    ("קונספט וכיוון קריאייטיבי", "Concept & Creative Direction",
     "לוחות השראה, סטיילינג וכיוון ויזואלי לפני שמתחילים ליצור.",
     "Moodboards, styling and visual direction before creation begins."),
]


def add_missing_columns() -> list[str]:
    """create_all() never alters existing tables: add any nullable column a model gained since."""
    inspector = db.inspect(db.engine)
    added = []
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            if not column.nullable:
                raise click.ClickException(f"{table.name}.{column.name} is NOT NULL; run init-db --drop")
            col_type = column.type.compile(dialect=db.engine.dialect)
            with db.engine.begin() as conn:
                conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}')
            added.append(f"{table.name}.{column.name}")
    return added


def register_cli(app):
    @app.cli.command("init-db")
    @click.option("--drop", is_flag=True, help="Drop all tables first (destroys data).")
    def init_db(drop):
        """Create database tables (and add columns added to models since)."""
        if drop:
            click.confirm("This will delete ALL data. Continue?", abort=True)
            db.drop_all()
        db.create_all()
        added = add_missing_columns()
        click.echo("Database tables created." + (f" Added columns: {', '.join(added)}" if added else ""))

    @app.cli.command("seed")
    def seed():
        """Create the admin; on a brand-new database also the starter category and services.
        Safe to re-run: once the admin exists nothing changes."""
        db.create_all()
        username = current_app.config["ADMIN_USERNAME"]
        if Admin.query.filter_by(username=username).first():
            click.echo(f"Admin '{username}' already exists; nothing to seed.")
            return
        password = current_app.config["ADMIN_PASSWORD"]
        if password == DEFAULT_ADMIN_PASSWORD:
            if current_app.config.get("SESSION_COOKIE_SECURE"):
                raise click.ClickException("Refusing the public default password in production. Set ADMIN_PASSWORD.")
            click.echo("  WARNING: using the default password. Change it after the first login.")
        admin = Admin(username=username)
        admin.set_password(password)
        db.session.add(admin)
        if Category.query.count() == 0:
            db.session.add_all(Category(slug=s, name_he=he, name_en=en, sort_order=i)
                               for i, (s, he, en) in enumerate(STARTER_CATEGORIES))
        if Service.query.count() == 0:
            db.session.add_all(Service(title_he=th, title_en=te, description_he=dh, description_en=de, sort_order=i)
                               for i, (th, te, dh, de) in enumerate(STARTER_SERVICES))
        db.session.commit()
        click.echo(f"Created admin '{username}', starter category and services.")

    @app.cli.command("seed-demo")
    @click.option("--count", default=8, show_default=True, help="Number of demo projects.")
    def seed_demo(count):
        """Demo projects with generated placeholder images (delete them from the admin later)."""
        from .storage import save_image
        category = Category.query.order_by(Category.sort_order).first()
        rng = random.Random(7)
        for n in range(1, count + 1):
            project = Project(slug=f"demo-campaign-{n}", title_he=f"קמפיין לדוגמה {n}",
                              title_en=f"Demo Campaign {n}", client="Demo Brand", year=2026,
                              description_he="פרויקט לדוגמה. אפשר למחוק אותו מאזור הניהול.",
                              description_en="A demo project. Delete it from the admin.",
                              category=category, is_featured=n <= 6, sort_order=n)
            for i in range(rng.choice((2, 3, 4))):
                size = rng.choice(((1200, 1500), (1500, 1000), (1200, 1200), (1000, 1400)))
                filename, w, h = save_image(_placeholder(size, rng))
                project.images.append(ProjectImage(filename=filename, width=w, height=h, sort_order=i,
                                                   is_cover=i == 0, alt_en="Demo image", alt_he="תמונה לדוגמה"))
            db.session.add(project)
        db.session.commit()
        click.echo(f"Added {count} demo projects.")

    @app.cli.command("export")
    @click.option("--out", default=None, help="Output folder (default: dist/).")
    def export(out):
        """Build the static site for Netlify into dist/ (then commit & push it)."""
        from .exporter import ExportError, export_site
        try:
            stats = export_site(app, out)
        except ExportError as exc:
            raise click.ClickException(f"Export stopped: {exc}") from exc
        click.echo(f"Exported {stats['pages']} pages and {stats['images']} images to {stats['out_dir']}")

    @app.cli.command("reset-password")
    @click.option("--username", default=None)
    def reset_password(username):
        """Set a new admin password from the command line (forgotten password)."""
        username = username or current_app.config["ADMIN_USERNAME"]
        admin = Admin.query.filter_by(username=username).first()
        if admin is None:
            raise click.ClickException(f"No admin '{username}'. Run `flask seed` first.")
        new = click.prompt("New password", hide_input=True)
        confirm = click.prompt("Repeat new password", hide_input=True)
        problem = validate_new_password(new, confirm, username)
        if problem:
            raise click.ClickException(problem[1])
        admin.set_password(new)
        db.session.commit()
        click.echo(f"Password for '{username}' updated.")


def _placeholder(size, rng) -> FileStorage:
    """A soft, abstract cream/beige composition (sun + arch), in the brand palette."""
    from PIL import Image, ImageDraw, ImageFilter

    w, h = size
    palette = [(245, 240, 232), (234, 225, 211), (214, 199, 176), (196, 176, 150), (168, 151, 127)]
    top, bottom = rng.sample(palette[:3], 2)
    img = Image.new("RGB", size)
    draw = ImageDraw.Draw(img)
    for y in range(h):  # vertical gradient
        k = y / h
        draw.line([(0, y), (w, y)], fill=tuple(int(top[c] * (1 - k) + bottom[c] * k) for c in range(3)))
    r = int(min(w, h) * rng.uniform(.18, .3))
    cx, cy = int(w * rng.uniform(.3, .7)), int(h * rng.uniform(.25, .45))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rng.choice(palette[2:]))
    aw = int(w * rng.uniform(.35, .55))
    ax = int(w * rng.uniform(.1, .9 - aw / w))
    draw.rounded_rectangle([ax, int(h * .55), ax + aw, h + aw], radius=aw // 2, fill=rng.choice(palette[1:4]))
    img = img.filter(ImageFilter.GaussianBlur(2))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return FileStorage(stream=buf, filename="demo.png")
