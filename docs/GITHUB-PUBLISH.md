# GitHub veröffentlichen

Dieses Verzeichnis ist bereits ein initialisiertes Git-Repository mit `main` und einem ersten Commit.

In der aktuellen ChatGPT-GitHub-Verbindung ist kein `create repository`-Vorgang verfügbar; daher konnte das neue Remote-Repository nicht automatisch angelegt werden.

Vorgeschlagener Repo-Name:

`xgs116-opnsense-mvxgs`

Empfehlung: zunächst **private** erstellen.

Danach im entpackten Repo:

```sh
git remote add origin https://github.com/Joka07/xgs116-opnsense-mvxgs.git
git push -u origin main
```

Alternativ kann das mitgelieferte `.bundle` geklont werden:

```sh
git clone xgs116-opnsense-mvxgs.bundle xgs116-opnsense-mvxgs
```
