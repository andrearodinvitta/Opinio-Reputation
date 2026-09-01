# 🛡️ Opinio Reputation Shield — Embudo Inteligente de Reseñas para Negocios Locales

Aplicación web completa y multi-tenant de gestión de reputación online para negocios locales (restaurantes, clínicas, salones de belleza, talleres, hoteles y comercios).

---

## 🚀 Inicio Rápido

Para iniciar el servidor localmente:

```bash
cd /Users/andreatorres/.gemini/antigravity-ide/scratch/review-funnel
./start.sh
```

O directamente con Python:
```bash
python3 server.py
```

### 📍 Accesos del Sistema

| Módulo | URL Local | Credenciales Demo |
| :--- | :--- | :--- |
| **🌐 Página Principal & Solicitud de Acceso** | [http://localhost:8080](http://localhost:8080) | Público |
| **👑 Panel de Superadministrador** | [http://localhost:8080/admin](http://localhost:8080/admin) | `admin@opinio.app` / `admin123` |
| **🏢 Acceso a Negocios Aprobados** | [http://localhost:8080/login](http://localhost:8080/login) | `soraya@example.com` / `admin123`<br>`bellavista@example.com` / `admin123` |
| **⭐ Embudo de Cliente (Soraya Nails)** | [http://localhost:8080/r/soraya-nails](http://localhost:8080/r/soraya-nails) | Escaneo QR / NFC |
| **⭐ Embudo de Cliente (Bella Vista)** | [http://localhost:8080/r/bella-vista](http://localhost:8080/r/bella-vista) | Escaneo QR / NFC |

---

## 🌟 1. Embudo de Reseñas (Lógica de Filtrado Inteligente)

```
[Cliente escanea QR en mesa / mostrador o acerca móvil a tarjeta NFC]
                               │
                               ▼
            [Landing Mobile-First (<50ms) /r/:slug]
              "¿Cómo fue tu experiencia hoy?" (1-5 ⭐)
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
        [4 o 5 estrellas]             [1, 2 o 3 estrellas]
                │                             │
                │                             ▼
                │                    [Intercepción Privada]
                │                    - Formulario "¿Qué ocurrió?"
                │                    - Selector de motivo (Atención, Tiempo, Calidad)
                │                    - Contacto opcional (WhatsApp / Email)
                │                    - 100% Privado (NUNCA llega a Google)
                │                    - Alerta inmediata al dueño del negocio
                ▼
  [Redirección Directa a Google Reviews]
  - Botón oficial directo a la ficha Google Maps
  - Contador regresivo de auto-redirección (3s)
  - Chips de elogios sugeridos copiables con 1 toque
  - Cliente satisfecho publica 5 estrellas en Google
```

---

## 👑 2. Sistema de Superadministrador con Aprobación Estricta

- **Sin registro abierto**: Los nuevos interesados deben rellenar el formulario de **"Solicitar Acceso"** en la web pública.
- **Estado Pendiente**: La solicitud queda registrada como `pending` y el usuario no puede iniciar sesión.
- **Panel Maestro (`/admin`)**:
  - **Aprobar Solicitud con 1 Clic**: Crea la cuenta del negocio en estado `active`, genera una contraseña temporal inicial segura y emite el enlace directo `/r/:slug`.
  - **Rechazar Solicitud**: Registra el motivo de rechazo.
  - **Directorio y Control**: Listado completo de comercios con opción de **Suspender / Desactivar** en cualquier momento (bloquea de inmediato el inicio de sesión y el embudo público).
  - **Impersonar**: Botón para acceder directamente al panel del negocio para soporte técnico.

---

## 🏢 3. Panel de Negocio (Gestión & Analíticas)

1. **Resumen & Analíticas en Tiempo Real**:
   - Total de valoraciones recibidas.
   - % de satisfacción de clientes.
   - Cantidad de reseñas negativas interceptadas en privado antes de llegar a Google.
   - Gráficos interactivos de distribución de 1 a 5 estrellas y flujo de conversión.

2. **Buzón Privado de Mejora**:
   - Listado de quejas y feedback de 1 a 3 estrellas.
   - **Botón directo de WhatsApp (`wa.me`)**: Abre chat con mensaje empático y personalizado para compensar al cliente.
   - Botones directos de llamada y correo.
   - Notas internas de seguimiento y cambio de estado (`Nuevo`, `Contactado`, `Resuelto`).
   - **Exportación a CSV**: Descarga en un clic de todas las opiniones recibidas.

3. **Cartelería QR & Enlace NFC**:
   - Generador de código QR de alta definición (descargable).
   - **Diseñador de Cartel Imprimible para Mesa / Mostrador (Table Tent & Stand Flyer)**: Vista lista para imprimir con el logo del negocio, código QR y llamada a la acción.
   - Enlace listo para grabar en tarjetas y placas NFC con guía paso a paso para la app gratuita **NFC Tools**.

4. **Personalización & Marca con Simulador en Vivo**:
   - Enlace oficial de Google Reviews con validador y comprobador.
   - Nombre del negocio, logo, color principal y secundario.
   - Textos de bienvenida y título del embudo.
   - **Simulador móvil en pantalla**: previsualiza en tiempo real los cambios estéticos dentro de un marco de smartphone.

---

## 📁 Estructura del Proyecto

```
review-funnel/
├── server.py              # Backend HTTP REST con SQLite y autenticación RBAC
├── reputation.db          # Base de datos SQLite local
├── start.sh               # Script de inicio rápido
├── README.md              # Documentación técnica
└── public/
    ├── index.html         # Landing page con simulador interactivo y formulario de solicitud
    ├── auth.html          # Login exclusivo para negocios aprobados
    ├── admin.html         # Panel maestro del Superadministrador
    ├── dashboard.html     # Panel del negocio (métricas, buzón WhatsApp, QR stand, personalizador)
    ├── funnel.html        # Embudo móvil ultrarrápido para el cliente (/r/:slug)
    ├── css/
    │   └── style.css      # Sistema de diseño moderno, tokens CSS y modo oscuro
    └── js/
        ├── admin.js       # Controlador del panel de Superadministrador
        ├── auth.js        # Manejador de login y sesiones
        ├── dashboard.js   # Controlador del panel de negocio
        └── funnel.js      # Controlador del embudo móvil de calificación
```
