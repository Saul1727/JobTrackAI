# JobTrack AI

Sistema de seguimiento de candidaturas de empleo con extracción y
generación de contenido asistidas por IA. Una extensión de Chrome captura
la oferta que se está viendo, un modelo de lenguaje (Google Gemini, con
Groq como respaldo automático) extrae sus datos estructurados, y un panel
web permite gestionar el histórico de candidaturas y generar un CV
adaptado a cada oferta, listo para descargar en PDF.

La aplicación es multiusuario: un mismo despliegue del backend admite
varias cuentas independientes, cada una con su propio inicio de sesión,
sus propias candidaturas y su propio CV base.

## Funcionalidades

- **Cuentas de usuario** con autenticación por token (JWT). Cada cuenta
  ve exclusivamente sus propios datos.
- **Extracción automática de ofertas**: la extensión de Chrome envía la
  URL y el contenido de la página activa; el backend usa un modelo de IA
  para extraer empresa, puesto, ciudad, salario, modalidad de trabajo,
  tecnologías, idiomas y experiencia requerida.
- **Seguimiento de candidaturas**: estado (guardada / aplicado /
  entrevista / oferta / rechazado), notas y fecha de seguimiento,
  editables desde el panel.
- **Generación de CV personalizado**: a partir de un CV base (PDF o
  Word) subido una vez, genera una versión adaptada a cada oferta en
  formato compatible con sistemas ATS, editable en el panel y
  descargable como PDF.
- **Exportación a Excel** del histórico completo de candidaturas.
- **Suite de tests automatizados** (pytest) que cubre autenticación,
  aislamiento de datos entre usuarios, CRUD de candidaturas, generación
  de CV y los mecanismos de reintento/respaldo frente a fallos de la IA.

## Arquitectura

| Componente  | Detalle |
|---|---|
| Backend     | Python, FastAPI, SQLModel (SQLAlchemy + Pydantic) |
| Base de datos | SQLite en desarrollo, PostgreSQL en producción |
| Frontend    | HTML/CSS/JavaScript sin framework ni build step |
| Extensión   | Chrome Manifest V3 (service worker + popup) |
| IA          | Google Gemini (`google-genai`), con Groq como respaldo |
| Autenticación | JWT (PyJWT) + hashing de contraseñas con bcrypt |
| Generación de PDF | reportlab |
| Exportación a Excel | openpyxl |

### Estructura del repositorio

```
radar-de-curro/
├── backend/
│   ├── app/
│   │   ├── main.py            # Punto de entrada de la aplicación
│   │   ├── auth.py            # Autenticación (JWT, hashing)
│   │   ├── models.py          # Modelos de base de datos (SQLModel)
│   │   ├── schemas.py         # Esquemas de la API (Pydantic)
│   │   ├── crud.py            # Capa de acceso a datos
│   │   ├── database.py        # Configuración de la conexión
│   │   ├── routers/           # Rutas HTTP (auth, candidaturas, cv-base)
│   │   └── services/          # Integración con IA, extracción y PDF
│   ├── frontend/index.html    # Panel web (servido por el propio backend)
│   └── tests/                 # Suite de pytest
├── extension/                 # Extensión de Chrome (Manifest V3)
└── render.yaml                 # Blueprint de despliegue en Render
```

## Puesta en marcha en local

### Requisitos

- Python 3.11+
- Una clave de API de [Google AI Studio](https://aistudio.google.com)
  (gratuita) para la extracción y generación por IA.

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # completar GEMINI_API_KEY
uvicorn app.main:app --reload
```

- Documentación interactiva de la API: `http://127.0.0.1:8000/docs`
- Panel web: `http://127.0.0.1:8000/panel`

### Tests

```bash
cd backend
pytest
```

### Extensión de Chrome

1. Ir a `chrome://extensions`, activar "Modo de desarrollador" y pulsar
   "Cargar descomprimida".
2. Seleccionar la carpeta `extension/`.
3. Al abrir el icono de la extensión por primera vez, se solicita la URL
   del backend (`http://127.0.0.1:8000` en local) y, a continuación,
   iniciar sesión o registrar una cuenta.

## Despliegue en producción

El backend puede desplegarse una única vez y ser usado por varias
personas, cada una con su propia cuenta. El despliegue requiere dos
servicios gratuitos, sin necesidad de tarjeta de crédito:

- **[Neon](https://neon.com)** — base de datos PostgreSQL gestionada.
  Necesaria porque el disco de la mayoría de plataformas de hosting
  gratuitas no es persistente: un redeploy borraría una base de datos
  SQLite local. Neon conserva los datos de forma permanente.
- **[Render](https://render.com)** — hosting del backend (FastAPI). En
  el plan gratuito, el servicio entra en reposo tras ~15 minutos de
  inactividad y tarda algo más de un minuto en responder a la primera
  petición tras despertar.

### 1. Base de datos

1. Crear una cuenta en [neon.com](https://neon.com).
2. Crear un proyecto nuevo.
3. Copiar la cadena de conexión (`postgresql://usuario:contraseña@...`).
   Se usa tal cual en el siguiente paso, sin modificarla.

### 2. Repositorio en GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<usuario>/<repositorio>.git
git push -u origin main
```

### 3. Backend en Render

1. Crear una cuenta en [render.com](https://render.com) (puede vincularse
   directamente con GitHub).
2. **Dashboard → New → Blueprint**, y seleccionar el repositorio. Render
   detecta `render.yaml` automáticamente y propone la configuración del
   servicio.
3. Al crear el servicio se solicitan tres variables de entorno (no se
   guardan en el repositorio, que es público):
   - `DATABASE_URL`: la cadena de conexión de Neon.
   - `GEMINI_API_KEY`: clave de [aistudio.google.com](https://aistudio.google.com).
   - `GROQ_API_KEY`: opcional, respaldo si Gemini falla.
4. El primer despliegue tarda unos minutos. El backend queda accesible
   en una URL del tipo `https://<nombre-del-servicio>.onrender.com`.
5. Verificar que `https://<url>/panel` carga correctamente y permite
   registrar una cuenta.

### 4. Acceso de otros usuarios

Al ser un repositorio público, cada persona puede:

1. Abrir `https://<url>/panel` y registrar su propia cuenta — no
   requiere ninguna configuración adicional.
2. Para usar la extensión de Chrome: descargar el repositorio (botón
   **Code → Download ZIP** en GitHub, o `git clone`), cargar la carpeta
   `extension/` como extensión sin empaquetar (ver más arriba), e
   introducir la URL del backend desplegado al abrir el icono por
   primera vez.

Ninguna cuenta adicional de Render, Neon, Gemini o Groq es necesaria por
parte de quienes solo usan la aplicación.

### Actualizaciones posteriores

Cualquier cambio subido a la rama conectada en Render (`git push`)
dispara un redeploy automático. La base de datos en Neon no se ve
afectada por un redeploy.

## Seguridad

- Las contraseñas se almacenan con hash bcrypt, nunca en texto plano.
- Las sesiones usan JWT firmado; cada usuario solo puede acceder a sus
  propios datos (verificado tanto en la capa de acceso a datos como en
  cada endpoint).
- `SECRET_KEY` debe configurarse con un valor propio y aleatorio en
  producción — el backend emite un aviso en el arranque si detecta que
  sigue usando el valor de ejemplo del repositorio.
- El archivo `.env` (credenciales y claves) está excluido del control de
  versiones.
