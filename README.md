# Gestión de solicitudes RESPEL

Aplicación Flask preparada para Render. Incluye inicio de sesión, importación y exportación Excel, formulario, edición, eliminación, búsqueda y dashboard. El proyecto se entrega sin datos reales ni registros precargados. Usa solo los nombres de columnas identificados en la imagen.

## Uso local

1. Instala las dependencias: `pip install -r requirements.txt`.
2. Genera una clave cifrada: `python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('CAMBIA_ESTA_CLAVE'))"`.
3. Configura `APP_USER`, `APP_PASSWORD_HASH` con el resultado del paso 2 y `SECRET_KEY` con una cadena aleatoria larga. En bash usa `export APP_USER=admin`; en PowerShell usa `$env:APP_USER='admin'`. Aplica el mismo procedimiento a las otras variables.
4. Ejecuta `python app.py` y abre `http://127.0.0.1:5000`.

En desarrollo, si no defines `DATABASE_URL`, se crea una base SQLite local. No uses el sistema de archivos de Render para guardar datos permanentes.

## Render

1. Sube los archivos a la raíz de un repositorio GitHub. Si mantienes la carpeta `respel_app` dentro del repositorio, indica `respel_app` como **Root Directory** al crear el servicio.
2. En Render selecciona **New → Blueprint** y conecta el repositorio. El archivo `render.yaml` declara una app web y PostgreSQL.
3. Define las variables `APP_USER` y `APP_PASSWORD_HASH` cuando Render las solicite. No ingreses la contraseña en texto plano en `APP_PASSWORD_HASH`.
4. Despliega. La tabla se crea automáticamente al iniciar. Activa respaldos de la base según tu plan y necesidades. Si cambias el modelo en el futuro, implementa migraciones.

## Excel y prioridades

Descarga la plantilla vacía desde **Importar Excel**. Se lee la primera hoja de archivos `.xlsx`, máximo 8 MB y 10.000 filas. Se reconocen encabezados sin importar mayúsculas o tildes; `Clientes RESPEL` y al menos otra columna reconocida son obligatorios. Se permiten celdas vacías, pero las filas sin cliente se omiten. La importación agrega filas, sin detectar duplicados. Da formato de texto a los teléfonos en Excel para preservar ceros iniciales.

La prioridad es una **regla operativa orientativa**, no una clasificación legal o sanitaria. Cerrada: estado cerrado, completado, finalizado, cancelado o no interesado. Alta: residuo peligroso, asbesto, químico, contaminado o REAS, excepto la expresión «no peligroso»; también estados urgente, pendiente, esperando, sin respuesta o por contactar. Media: cotización, agendar, visita, llamar o seguimiento. Baja: los demás. Modifica `priority()` en `app.py` para ajustar la regla. Las cantidades del dashboard representan solicitudes y no masa o volumen.

Diseño inspirado en los tonos verdes y la estética ambiental de respel.cl, sin usar sus logos ni afirmar vinculación con esa empresa.
