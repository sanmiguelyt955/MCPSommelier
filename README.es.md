# 🍷🔌 MCPSommelier (español)

**El buscador inteligente de conectores (MCP) para personas e IAs.** Dile lo que quieres hacer, **en cualquier idioma**, y te da **los mejores conectores para eso**, del mejor al peor. **Primero los que ya tienes**, si sirven, porque no hay que instalar nada. Luego los mejores nuevos, con avisos de costo, instalación y confianza.

Hermano de [RepoSommelier](https://github.com/sanmiguelyt955/RepoSommelier): aquel busca repos, este busca conectores.

```bash
python3 mcpsommelier.py "hacer un video de producto y publicarlo en TikTok"
python3 mcpsommelier.py "mandar facturas por correo" --free
```

## Qué hace
1. **Entiende** tu necesidad y la separa en tareas (por ejemplo: «hacer el video» y «publicarlo»).
2. **Revisa primero tus conectores** (`data/inventory.json`).
3. **Busca** en el registro oficial de conectores MCP y en GitHub.
4. **Revisa** cada uno: si está alojado en la nube o hay que instalarlo, si pide clave o inicio de sesión, si cobra, y si es oficial o una copia de terceros.
5. Un **juez** (Gemini) califica de 0 a 10 qué tanto te sirve y qué tarea cubre.
6. Te dice **qué partes de tu necesidad quedan cubiertas** y cuáles todavía no tienen conector.
7. Los que no sirven donde estás salen aparte, con un **plan B legítimo**.

## De paga y sustitutos
- **El precio nunca baja la calificación:** el mejor del mercado puede costar 1 dólar. Los de paga conservan su calificación real y solo se **mueven** a su propia sección, «💳 De paga», con el precio cuando lo dice, para que tú decidas.
- Una tarea solo cuenta como cubierta si el juez le da 6/10 o más a un conector para esa tarea.
- **Sustitutos:** para cada tarea sin conector (y para los apartados), busca **repos de GitHub que hagan lo mismo** (una librería, programa o app que el agente pueda correr). Solo sustitutos legítimos: revisa la licencia y las reglas del servicio.

**Seguridad:** solo lee. Nunca instala, conecta ni autoriza nada. Las claves se conectan en tu app, nunca en un chat.
