# Shop Titans BiS Tracker

Generador reproducible de una galería **Best in Slot** de Shop Titans.

El proyecto cruza dos fuentes públicas que cambian con el tiempo:

- **Shop Titans Data Spreadsheet (Kabam)**: fuente de verdad del dominio del juego. De sus hojas se obtienen blueprints, clases/promociones de héroe, recursos, componentes y recetas.
- **ST Central Hub**: aporta únicamente las relaciones BiS entre héroes y objetos. Sus nombres se validan y canonicalizan contra el spreadsheet oficial.

El resultado es `docs/index.html`: **un único HTML autocontenido**, con las imágenes embebidas en Base64 y filtros por héroe, recursos básicos y componentes.

## Estructura

```text
shop-titans-bis-tracker/
├── shop_titans_bis/          # package Python
│   ├── __init__.py
│   ├── sources.py            # descarga los CSV oficiales
│   ├── spreadsheet.py        # procesa los CSV locales
│   ├── stcentral.py
│   ├── images.py
│   ├── render.py
│   ├── changelog.py
│   ├── blueprints.py
│   ├── util.py
│   └── update.py             # orquestación interna
├── source/                   # snapshots CSV descargados
│   ├── BLUEPRINTS.csv
│   ├── FULL_MOON_FUSIONS.csv
│   ├── HEROES.csv
│   ├── QUEST_COMPONENTS.csv
│   └── RESOURCE_BINS.csv
├── data/
├── assets-cache/
├── docs/
├── templates/
├── tests/
├── config.json
├── requirements.txt
└── update.py                 # única entrada Python externa
```

`data/seed.json` queda reservado a excepciones técnicas de assets (`image_slugs`). No contiene colecciones de héroes, materiales ni blueprints. Cuando hay cambios de datos, el catálogo derivado se guarda también en `data/catalog.json` para trazabilidad y ejecución offline.

## Crear y publicar el repositorio desde Windows

Necesitas tener instalados:

- **Git**
- **GitHub CLI (`gh`)**

Antes de ejecutar el script por primera vez, configura tu identidad de Git:

```bat
git config --global user.name "TU_NOMBRE"
git config --global user.email "TU_EMAIL"
```

Después autentícate en GitHub CLI:

```bat
gh auth login
```

Finalmente ejecuta este comando:

```bat
setup-github.bat
```

Por defecto creará un repositorio público llamado `shop-titans-bis-tracker`, hará el primer `push`, intentará activar Pages en modo GitHub Actions y te mostrará la URL pública. Para usar otro nombre:

```powershell
.\setup-github.ps1 -RepoName mi-shop-titans-bis
```

## URL pública con GitHub Pages

Si el repositorio se llama `shop-titans-bis-tracker` y tu usuario es `TU_USUARIO`, la URL normal será:

```text
https://TU_USUARIO.github.io/shop-titans-bis-tracker/
```

El workflow `.github/workflows/pages.yml` publica automáticamente `docs/` en GitHub Pages en cada `push` a `main`.

### Activar Pages la primera vez

1. Crea un repositorio público en GitHub y sube este contenido a `main`.
2. En GitHub entra en **Settings → Pages**.
3. En **Build and deployment → Source**, selecciona **GitHub Actions**.
4. Abre **Actions** y ejecuta manualmente `Deploy GitHub Pages` si no se lanza con el primer push.
5. Al terminar, GitHub mostrará la URL pública del deployment.

## Actualización automática

`.github/workflows/update.yml` se ejecuta:

- manualmente (`workflow_dispatch`), y
- todos los lunes a las 06:17 UTC.

El minuto 17 es intencionado: evita la franja exacta de comienzo de hora, donde GitHub advierte de mayores retrasos en workflows programados.

El job:

1. descarga del spreadsheet oficial las hojas configuradas
2. construye el catálogo canónico del juego
3. descarga la página BiS de ST Central
4. valida y canonicaliza héroes e items de ST Central contra el catálogo oficial
5. obtiene y valida recetas, recursos, componentes e imágenes
6. regenera `docs/index.html`
7. actualiza snapshots y `CHANGELOG.md`
8. hace commit **solo si existen cambios**

El mismo workflow despliega `docs/` en GitHub Pages después de actualizar/validar. Esto es intencionado: los `push` realizados por un workflow con `GITHUB_TOKEN` no disparan normalmente otro workflow. `pages.yml` queda además para desplegar cambios que tú hagas manualmente mediante un `push` a `main`.

## Ejecutar localmente

Requiere Python 3.12+.

```bash
python -m venv .venv
```

Windows:

```cmd
.venv\Scripts\activate
pip install -r requirements.txt
python update.py
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python update.py
```

Para ejecutar los tests:

```cmd
python -m pytest -q
```

Para regenerar el HTML **sin Internet**, utilizando el snapshot y la caché ya versionados:

```cmd
python update.py --offline
```

## Seguridad frente a cambios de estructura

El actualizador es deliberadamente conservador. Si detecta muy pocos objetos, recetas vacías, héroes/items de ST Central que no existen en el spreadsheet, materiales que no pertenecen a los catálogos oficiales o una imagen no resoluble, falla antes de sobrescribir el snapshot válido. Esto es preferible a publicar silenciosamente datos incompletos.

La validación de valores se hace contra el propio spreadsheet; el código solo conoce el esquema necesario para localizar las tablas y relacionar sus columnas. La configuración de hojas está en `config.json`. Si Kabam cambia el esquema de una hoja o ST Central cambia su HTML, el fallo debe ser explícito antes de publicar.

## Imágenes

Las imágenes actuales se conservan en `assets-cache/` para que el build sea reproducible y para que la página siga funcionando si el servidor de imágenes está temporalmente caído. El HTML publicado las embebe como `data:` y no hace peticiones externas al abrirse.

## Fuentes y atribución

- ST Central Hub: recomendaciones BiS.
- Shop Titans / Kabam: spreadsheet oficial y assets del juego.

Este repositorio es una herramienta de comunidad y no está afiliado, patrocinado ni encargado por Kabam Games, Inc. o ST Central. Los nombres e imágenes del juego pertenecen a sus respectivos titulares.
