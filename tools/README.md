# Outils d'analyse legacy

Ces outils sont **hors processus** : Méridian normalise leur sortie en `Observation`.

## ABAP

```bash
npm install --prefix tools/abaplint
node tools/abaplint/analyze.js chemin/mon_programme.abap
```

## RPGLE

Voir [rpgle/README.md](rpgle/README.md) : téléchargement des jars Maven, puis :

```bash
javac -encoding UTF-8 -cp "tools/rpgle/lib/*" -d tools/rpgle/classes tools/rpgle/Analyze.java
```

## PL/I

```bash
cd tools/pli && ./generate.sh
```

## PowerBuilder

Aucune dépendance : les `.pbl` sont extraits en sources par le sidecar.

## Oracle Forms

Le sidecar traite les exports XML. Les `.fmb`/`.fmx` binaires restent une couverture partielle.
