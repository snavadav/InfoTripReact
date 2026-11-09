# Despliegue en AWS (plan gratuito)

Esta guía publica InfoTrip en internet con HTTPS, en un solo servidor EC2 de AWS con Docker. Cuesta $0 mientras
duren los créditos del plan gratuito.

Se probó completa en local el 8 de noviembre de 2026: Caddy con HTTPS, restauración del respaldo, páginas, API,
planeador y límites de peticiones.

```
Internet ──HTTPS──▶ Caddy (certificado automático) ──▶ nginx (fotos) ──▶ Django/gunicorn ──▶ PostgreSQL + Redis
```

**Tiempo:** de 1 a 2 horas la primera vez.

**Qué necesitas:**

- una tarjeta, que AWS pide para verificar tu identidad aunque no cobre;
- tu teléfono;
- el correo y la contraseña de aplicación del proyecto (Gmail).

## Costo y plan gratuito

Las cuentas nuevas de AWS entran al **plan gratuito**:

- **Créditos:** US$100 al registrarte y hasta US$100 más al completar actividades de introducción.
- **Duración:** la cuenta dura **6 meses** o hasta que se acaben los créditos, lo que pase primero.
- **Al terminar:** la cuenta se cierra, salvo que la cambies a un plan de pago. **No te cobran nada** mientras no hagas
  ese cambio.

Revisa las condiciones vigentes en https://aws.amazon.com/free/ antes de empezar.

| Recurso | Consumo aproximado de créditos |
|---|---|
| EC2 `t3.small` (2 vCPU, 2 GB), encendido todo el mes | ≈ US$15 al mes |
| Disco de 30 GB (gp3) | ≈ US$2.4 al mes |
| IP pública (IPv4) | ≈ US$3.6 al mes |
| **Total** | **≈ US$21 al mes**: US$100 alcanzan para unos 4.5 meses, y US$200 para los 6 meses completos |

**¿Por qué `t3.small` y no `t3.micro`?** Corren a la vez Django con 3 procesos, PostgreSQL, Redis, nginx y Caddy. Con
1 GB de memoria, el servidor se queda sin memoria al construir la imagen o con varias visitas a la vez.

## Paso 1. Crear la cuenta y la alerta de gastos

1. Regístrate en https://aws.amazon.com/free/ y elige el **plan gratuito** (Free plan).
2. Activa la verificación en 2 pasos (MFA) del usuario raíz: *nombre de la cuenta → Security credentials → Assign
   MFA*.
3. Crea una alerta de presupuesto en *Billing and Cost Management → Budgets → Create budget → Use a template →
   Zero spend budget*. Pon el correo del equipo. Te avisa si algo empieza a costar dinero real.
4. Arriba a la derecha elige la región **US East (N. Virginia) `us-east-1`**. Es de las más baratas y tiene todos
   los tipos de servidor. La latencia desde Jalisco es aceptable.

## Paso 2. Crear el servidor (EC2)

En *EC2 → Launch instance*:

| Campo | Valor |
|---|---|
| Name | `infotrip` |
| Imagen (AMI) | **Ubuntu Server 24.04 LTS** (64-bit x86) |
| Instance type | **t3.small** |
| Key pair | *Create new key pair* → `infotrip`, tipo ED25519, formato `.pem`. Guárdala **fuera de OneDrive**, por ejemplo en `C:\Users\<tú>\.ssh\infotrip.pem`; sin ella no puedes entrar al servidor. |
| Network settings | Marca **Allow SSH traffic from: My IP**, **Allow HTTPS traffic from the internet** y **Allow HTTP traffic from the internet**. |
| Storage | **30 GiB gp3** |

Pulsa *Launch instance*.

Después, en *EC2 → Elastic IPs → Allocate Elastic IP address*, crea una IP y asóciala con *Actions → Associate* a la
instancia `infotrip`. Así la dirección no cambia si reinicias el servidor. **Anota la IP.**

## Paso 3. Dominio gratuito (DuckDNS)

Los navegadores solo dan la ubicación en sitios con HTTPS, y HTTPS necesita un nombre de dominio.

1. Entra a https://www.duckdns.org con una cuenta de GitHub o de Google.
2. Crea un subdominio, por ejemplo `infotrip-jalisco`. Quedará `infotrip-jalisco.duckdns.org`.
3. En *current ip* escribe la Elastic IP del paso 2 y pulsa *update ip*.

Compruébalo desde tu computadora. Debe responder con la IP de AWS:

```bash
nslookup infotrip-jalisco.duckdns.org
```

## Paso 4. Preparar el servidor

Desde PowerShell en tu computadora:

```bash
ssh -i $HOME\.ssh\infotrip.pem ubuntu@infotrip-jalisco.duckdns.org
```

Si Windows avisa que la llave tiene permisos demasiado abiertos, quítale el acceso a los demás usuarios:

```bash
icacls $HOME\.ssh\infotrip.pem /inheritance:r /grant:r "$($env:USERNAME):R"
```

Ya dentro del servidor, instala Docker desde los repositorios de Ubuntu:

```bash
sudo apt update && sudo apt -y upgrade
```

```bash
sudo apt -y install docker.io docker-compose-v2 git
```

```bash
sudo usermod -aG docker ubuntu
```

Crea 2 GB de memoria de intercambio, un respaldo por si la memoria se llena al construir la imagen:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Sal con `exit` y vuelve a entrar con `ssh` para que el permiso de Docker aplique.

## Paso 5. Descargar el proyecto y configurarlo

```bash
git clone https://github.com/snavadav/InfoTripReact.git infotrip && cd infotrip
```

```bash
cp .env.docker.aws.example .env.docker && chmod 600 .env.docker
```

Genera las dos claves aleatorias. Cópialas en el siguiente paso y no las compartas:

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64)); print('CLAVE_BD=' + secrets.token_urlsafe(32))"
```

Edita el archivo con `nano .env.docker`. Guarda con Ctrl+O, Enter, y sal con Ctrl+X.

- Llena todo lo marcado con **CAMBIAR**: dominio, correos, `SECRET_KEY`, contraseña de la base de datos (la misma en
  `POSTGRES_PASSWORD` y `DB_PASSWORD`) y la contraseña de aplicación de Gmail.

## Paso 6. Subir tu base de datos

En **tu computadora**, desde la carpeta del proyecto, exporta tu base local. El respaldo queda en
`C:\Users\<tú>\infotrip-respaldos\`, fuera de OneDrive:

```bash
powershell -ExecutionPolicy Bypass -File scripts\exportar_base.ps1
```

Súbelo al servidor. Cambia el nombre del archivo por el que mostró el script:

```bash
scp -i $HOME\.ssh\infotrip.pem $HOME\infotrip-respaldos\infotrip-AAAA-MM-DD-HHMM.dump ubuntu@infotrip-jalisco.duckdns.org:~/base.dump
```

## Paso 7. Arrancar y restaurar

En el **servidor**, dentro de `~/infotrip`. La primera vez, construir la imagen tarda unos 5 minutos:

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml --env-file .env.docker up -d --build
```

Restaura la base. Primero se detiene la aplicación para que nadie escriba mientras tanto:

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml --env-file .env.docker stop web avisos nginx
```

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml --env-file .env.docker cp ~/base.dump db:/tmp/base.dump
```

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml --env-file .env.docker exec db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges /tmp/base.dump && rm /tmp/base.dump'
```

```bash
docker compose -f docker-compose.yml -f docker-compose.aws.yml --env-file .env.docker up -d
```

Borra la copia del servidor. Ya está dentro de la base y contiene datos de cuentas:

```bash
rm ~/base.dump
```

Para no escribir esos `-f` cada vez, crea un atajo que dure mientras tengas abierta la sesión:

```bash
alias dc='docker compose -f docker-compose.yml -f docker-compose.aws.yml --env-file .env.docker'
```

## Paso 8. Comprobar

- Abre `https://infotrip-jalisco.duckdns.org`. El candado debe aparecer: Caddy pide el certificado solo, en menos de
  un minuto.
- `https://…/health/` debe responder `{"status": "ok"}` o similar.
- Recorre en el celular: registro (el código llega por correo), mapa, **Cerca de mí** (pide permiso de ubicación),
  ficha, reseña, costos, Mis viajes, planeador y comentarios.
- Si algo falla, revisa los registros:

```bash
dc logs --tail 100 web caddy
```

## Paso 9. Personal y moderación

Tu cuenta y las del equipo vienen en la base que restauraste. Si hace falta una cuenta de administrador nueva:

```bash
dc exec web python manage.py createsuperuser
```

Para dar acceso de moderación a una persona del equipo, después de que se registre en el sitio:

```bash
dc exec web python manage.py crear_moderacion --agregar correo@ejemplo.com
```

## Mantenimiento

**Actualizar a la última versión de `master`.** Las migraciones se aplican solas al arrancar.

```bash
cd ~/infotrip && git pull && dc up -d --build
```

**Respaldos.** El servicio `respaldos` guarda cada día la base y las fotos en el mismo servidor, y conserva 14 días.
Bájalos a tu computadora al menos una vez por semana: si el servidor se pierde, se pierden con él.

Primero, en el **servidor**, copia los respaldos a tu carpeta. El volumen de Docker solo lo puede leer root:

```bash
rm -rf ~/respaldos && sudo cp -r /var/lib/docker/volumes/infotrip_respaldos/_data ~/respaldos && sudo chown -R ubuntu ~/respaldos
```

Luego, en **tu computadora**, bájalos:

```bash
scp -i $HOME\.ssh\infotrip.pem -r ubuntu@infotrip-jalisco.duckdns.org:~/respaldos $HOME\infotrip-respaldos\servidor
```

Cómo restaurar un respaldo: [operacion.md](operacion.md).

**Cuando todo funcione por HTTPS** durante unos días, sube `SECURE_HSTS_SECONDS` a `31536000` en `.env.docker` y
ejecuta `dc up -d`.

**Antes del mes 5 del plan gratuito**, decidan qué hacer:

1. Pasar a plan de pago: ≈ US$21 al mes con esta configuración.
2. Mover el sitio a otro proveedor: es el mismo Docker, se repiten los pasos 4 a 8.
3. Apagarlo: baja los respaldos primero.

## Seguridad

- Nunca subas `.env.docker` a git. Ya está en `.gitignore`.
- La llave `.pem` solo en tu computadora y fuera de OneDrive.
- El puerto 22 (SSH) queda abierto solo para tu IP. Si cambia tu IP, edita la regla en *EC2 → Security Groups*.
- nginx no expone puertos: todo entra por Caddy, que fija la IP real del visitante. Así nadie puede saltarse HTTPS ni
  inventar su IP para evadir los límites de intentos.
- Los registros de web, nginx y Caddy se rotan (3 archivos de 10 MB por servicio), como dice el aviso de privacidad.

## Problemas comunes

| Síntoma | Causa probable |
|---|---|
| El navegador dice que el certificado no es válido | DuckDNS todavía no apunta a la IP correcta, o los puertos 80/443 no están abiertos en el grupo de seguridad. Revisa con `dc logs caddy`. |
| "Bad Request (400)" | `ALLOWED_HOSTS` no coincide exactamente con el dominio. |
| Error 403 al iniciar sesión o cerrar sesión | Falta `DETRAS_DE_PROXY_HTTPS=True`. |
| No llegan los correos | Contraseña de aplicación incorrecta, o `EMAIL_BACKEND` sigue en `console`. Prueba con `dc exec web python manage.py sendtestemail tu@correo.com`. |
| "Cerca de mí" no pide ubicación | El sitio no está en HTTPS, o el navegador tiene bloqueado el permiso. |
| El servidor se vuelve muy lento | Falta memoria: revisa con `free -h` que la memoria de intercambio esté activa. |
