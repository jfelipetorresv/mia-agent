# CIERRE — 2026-07-20 · Ola 2: lectura del expediente, guardián de citas, jurisdicción y Panel

Rama `feat/fase1-inc1-cleanup-scaffolding`. **7 commits nuevos hoy, NINGUNO pusheado** (Pipe aprueba el push).
Esta entrada es la más reciente: **empezar por aquí.**

## 1 · Entorno: dos cosas que cambiaron de verdad

**(a) Por primera vez se logró mantener MIA viva desde la sesión del asistente.** Los servicios sobreviven
si se lanzan con el mecanismo de fondo del harness (`run_in_background`), a diferencia de `Start-Process`,
que muere al terminar el comando. Esto destrabó la **verificación visual**, que llevaba sesiones dándose por
imposible: hoy se recorrieron las 11 pantallas con navegador real, se tomaron capturas y se forzaron caídas
de servidor para ver cómo reacciona el producto. Documentado en `docs/trampas-entorno-windows.md` §3.

**(b) Se encontró y cerró un bloqueante silencioso en la base de datos.** Las migraciones **044, 045 y 046
no constaban en el ledger** `mia_schema_migrations`: la 045 y la 046 se habían aplicado a mano en la sesión
anterior sorteando el landmine de `setup_db.ps1`, y **la 044 (salud de guías) nunca había corrido**.
`/health` reportaba **41 de 44** y el blindaje del instalador habría frenado el arranque en una máquina
limpia. Se aplicaron por el runner real. Verificado hoy en vivo:

```
{"status":"ok","db":true,"pgvector":"0.8.2","migrations_expected":44,"migrations_applied":44,
 "checkpointer":true,"provenance_ready":true}
```

## 2 · Qué se commiteó hoy

| Commit | Qué |
|---|---|
| `00c4c17` | **Lectura adaptativa del expediente.** Muere el literal `top_k=8`. El tamaño de lectura se deriva en cada turno de tres señales: cuánto material hay indexado, cuánto cabe en el presupuesto real del nodo más estrecho, y qué tan exigente es la pregunta (heurística determinista, sin modelo). Piso inviolable en 8. **Trampa cerrada que habría arruinado el cambio en silencio:** `hnsw.ef_search` nunca se fijaba, y con el valor de fábrica de pgvector (40) subir los candidatos por encima de ~40 **degrada el recall sin avisar**; ahora se fija en la misma transacción. Además dedup, tope por documento y expansión a fragmentos contiguos (apagada por defecto). Suite nueva `test_retrieval_adaptativa` 59/59. |
| `9516833` | **Guardián de citas en PROYECTOS** (no lo tenía: un proyecto podía afirmar normas y jurisprudencia sin una sola marca `[VERIFICAR]`). **Detalle que hace que el arreglo sirva:** se movió el punto de emisión del evento SSE para que el texto salga DESPUÉS de verificarse — sin eso, el nodo nuevo habría sido decorativo. **Y el arreglo del defecto más grave de la sesión** (ver §4). Gates: `test_projects` 59/59 · `doc_citation_guard` 38/38. |
| `03d861f` | **Ordenamiento aplicable y procedencia.** L3 declara ahora bajo qué reglas trabaja el despacho, en dos ramas (sin ordenamiento declarado: prohibición de nombrar articulado, códigos, corporaciones o bases normativas de un país; con ordenamiento declarado: cita el suyo con normalidad). Más una política de procedencia: no se atribuye al expediente ni al despacho nada que no haya llegado sellado en ese turno. **Y se cableó la jurisdicción del despacho al estado en el primer nodo del turno** — antes solo llegaba por el nodo de investigación, que en proyectos nunca corre. `jurisdiction_agnostic` pasa de 75 a **104/104**. |
| `444d3a1` | **Rediseño por capas.** Capa 1 tokens (escala tipográfica semántica de seis roles, tres radios, dos elevaciones, escala de espaciado, contraste subido donde caía bajo el mínimo accesible — eran justo los avisos de responsabilidad — y regla global de movimiento reducido, que **no existía en ninguna parte del producto salvo la bienvenida**). Capa 2 primitivas (`Card` rescatada, `PageShell`, `SectionTitle`, `lib/motion.ts`). Capa 3 pantallas: **Panel primero en la navegación y aterrizaje del login**, consumiendo lo que ya existía construido y sin exponer (`/api/setup/status` con los 7 pasos en lenguaje llano, salud de guías, gasto del mes, tareas programadas). |
| `872a7ec` | `docs/diseno-soul-onboarding.md` (rediseño del perfil del despacho, **diseñado no implementado**) + `docs/trampas-entorno-windows.md`. |
| `96d3449` | **Tres componentes literalmente desaparecían en tema oscuro** (`MissionBoard`, `MicButton`, `MailboxSectionLoader`): usaban la paleta cruda de Tailwind sin un solo token, así que en oscuro eran una isla gris clara dentro del negro. Se renderizan en pantallas primarias. |
| `aaa3d1a` | Los agentes del despacho no salían nunca como chips en el chat vacío: el corte a 6 guías se aplicaba ANTES de anexar las personas. Capacidad construida que el abogado no podía ver. |

## 3 · La decisión de Pipe que redefine el siguiente bloque

Se le presentó que la lectura adaptativa, con los valores de fábrica, **multiplicaba el gasto de IA por
turno entre 11 y 20 veces**. Su respuesta, textual:

> *"no se puede establecer como funciona Claude code o codex? al fin y al cabo su motor será uno de ellos"*

Es superior a las tres opciones que se le ofrecieron. En vez de calcular de antemano cuánto leer, **exponer
la búsqueda como una herramienta y dejar que el modelo pida más material cuando le falte**, igual que hacen
las herramientas agénticas de código. Así una pregunta trivial cuesta poco, una difícil lee lo que necesite,
y nadie tiene que adivinar una proporción: el coste se ajusta solo.

**Queda como el rediseño pendiente de más valor — "lectura agéntica".** Mientras tanto la cobertura quedó
en `0.22` (≈7 veces más lectura que antes, en vez de ≈20), conservando la promesa que custodia el gate `a1`:
en un expediente grande Mia lee una fracción real del material, no una muestra simbólica. Se probó `0.15` y
rompía justo esa promesa. El valor es **provisional** y así está escrito en `backend/mia/config.py`.

## 4 · Los hallazgos graves (lo más valioso de la sesión)

**(a) El guardián certificaba en verde citas inventadas.** Defecto **PREEXISTENTE** —afectaba ya al flujo de
asuntos que el despacho usa— que el cambio de hoy agravaba al multiplicar las claves cosechadas. El cotejo de
respaldo era bidireccional y no respetaba fronteras numéricas: con *"Decreto 1082 de 2015"* en el expediente,
un *"Decreto 108"* alucinado salía marcado **"Con respaldo"**, con visto verde y **atribuido a un archivo y
un folio reales**. Igual con *"Ley 143"* dentro de *"Ley 1437 de 2011"* y *"Sentencia C-35"* dentro de
*"C-355 de 2006"*. Es la regla dura del producto al revés: marcar de más es inofensivo, respaldar de más
destruye la única razón por la que un abogado confiaría en esto. **Lo encontró un verificador adversarial
ejecutando una sonda, no leyendo.** El test que decía cubrirlo solo ejercitaba la dirección ya blindada.

**(b) Fuga de jurisdicción capturada en vivo.** Un despacho de prueba vacío y sin país configurado preguntó
qué exige la ley para que un contrato sea válido, y recibió derecho de un país concreto: cinco citas de
articulado, una transcripción verbatim entrecomillada y el ofrecimiento de consultar una base normativa
nacional. Remató afirmando que era *"conocimiento consolidado del despacho"* — con el despacho vacío.
**Matiz honesto:** el agente que endureció el prompt **no pudo reproducirla en tres intentos** con el código
anterior. La lectura correcta no es que no existiera, sino que **es intermitente** — lo que la hace más
peligrosa, no menos, porque una fuga que aparece una de cada varias veces es la que se cuela a un escrito.
Confirma que la instrucción sola no basta y que el guardián determinista es imprescindible.

**(c) El Panel inventaba ceros** cuando la fuente de cifras fallaba: con el servidor de cifras caído afirmaba
*"0 borradores aprobados · 0 horas ahorradas · USD 0.00"*, indistinguible de un dato real. **Un cero es una
afirmación, no un dato ausente.** Era además una regresión: el código anterior se quedaba en esqueleto —feo,
pero nunca mentía. Se arregló y se demostró en navegador forzando la caída de la fuente en cinco escenarios.

**(d) La regla de "reducir movimiento" congelaba los indicadores de trabajo en curso.** Con esa preferencia
activada (ajuste común de Windows), el abogado veía una rueda detenida y no podía distinguir *"analizando"*
de *"colgada"*. Habría reenviado la consulta creyendo que MIA se colgó.

**(e) El dedup borraba la fuente primaria** cuando un documento del expediente citaba a otro: la pieza
original desaparecía del prompt con su archivo y su folio, y Mia solo podía anclar al escrito que la citaba.

## 5 · NO verificado (honesto)

- **La regresión completa de suites NO se corrió.** No cabe en el tiempo disponible; se corrieron **por
  tramos** las suites tocadas y sus adyacentes. La revalidación final dejó 11 gates en verde, incluidos los
  dos HALT (`test_rls` 19/19, `check_env_pins` 10/10).
- **Ningún gate corre contra un modelo real.** Que la instrucción de ordenamiento **de verdad suprima el
  prior del modelo está SIN PROBAR**: exige un benchmark ciego en vivo. **Es la brecha más grande de la
  sesión.** Todo lo demás va con modelos dobles.
- Los conteos de tokens salen de una heurística del propio test, no de un tokenizador real: todas las
  conclusiones de presupuesto heredan ese error.
- **No se midió coste ni latencia reales** del cambio de lectura, ni el recall del HNSW con `ef_search` alto
  (se confirmó que el parámetro se fija, no que el ranking mejore).
- **La rama sigue sin push.** Pipe aprueba.
- El rediseño del perfil del despacho está **diseñado y documentado, no implementado**.

## 6 · Riesgos señalados por los verificadores y NO cerrados

1. **`backend/mia/agents/warroom.py`** renderiza documentos **sin presupuesto ni recorte**, y ahora puede
   recibir muchos más fragmentos que antes. Es el candidato más probable a desbordar la ventana.
2. **`context_recovery.py`** recorta por mitades fijas en vez de por presupuesto.
3. **La Sala de estrategia podría quedar en la rama restrictiva de jurisdicción**: llama a
   `build_graph_system` con un estado que no viene del grafo y puede no traer `jurisdictions`.
4. `cn()` usa `twMerge` sin configurar, así que toda la escala tipográfica nueva se clasifica como color y
   un token de tamaño combinado con uno de color **pierde el tamaño en silencio**. Arreglo de una línea
   (`extendTailwindMerge`), no aplicado.
5. En 3 de las 4 políticas de modelo soportadas **no hay prefix caching**, así que las capas nuevas de
   prompt se pagan enteras en cada llamada. La conclusión de coste sobrevive (419 tokens sobre 200.000),
   pero el mecanismo que se citó como justificación es falso para la mayoría de instalaciones.
6. Siguen abiertas las **2 suites rojas de carpetas** (`test_matter_folder`, `test_matter_folders_multi`) y
   **no existe ni un solo test de "carpeta vinculada a un PROYECTO"** — que es justo el escenario que falló
   en producción.

## 7 · Pendiente de Pipe (no es código)

- Decidir el **push** de la rama.
- **Lectura agéntica**: es su propia decisión de diseño y el bloque de más valor pendiente (§3).
- Aparecieron en su escritorio **dos archivos ajenos a MIA** (`Informe-Lucy-*.json`, del producto
  `lexter-os`): pendiente de que decida qué hacer con ellos.
- Sigue pendiente de sesiones anteriores: registrar las **apps OAuth** de Gmail/Outlook/OneDrive y verificar
  el inc. 3 en vivo.

---

