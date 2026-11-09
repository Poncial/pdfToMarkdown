# pdfToMarkdown

Convertit des PDF en Markdown, avec une mise en forme pensée pour être lue par une IA
(titres hiérarchisés, paragraphes recollés, tableaux, sans notes de bas de page ni numéros de page).

## Structure

| Dossier | Contenu |
|---|---|
| `01_scripts/` | Script à lancer : `convert_pdfs.py` |
| `02_inputfiles/` | PDF à convertir (entrée) |
| `03_outputFiles/` | Fichiers Markdown produits (sortie) |
| `04_functions/` | Fonctions utilisées par le script |

Fonctions de `04_functions/` :
- `pdf_cleanup.py` : efface en mémoire notes de bas de page, numéros de page, en-têtes/pieds courts et appels de note (le PDF d'origine n'est pas modifié).
- `pdf_to_markdown.py` : convertit un PDF avec `pymupdf4llm`, puis applique le post-traitement.
- `postprocess_markdown.py` : normalise les niveaux de titre, fusionne les lignes d'un paragraphe, recolle puces et mots coupés, retire les en-têtes/pieds répétés.

## Installation

```bash
pip install -r requirements.txt
```

## Utilisation

1. Déposer les PDF dans `02_inputfiles/`.
2. Depuis la racine du projet :

   ```bash
   python 01_scripts/convert_pdfs.py
   ```

3. Récupérer les fichiers `.md` (même nom que le PDF) dans `03_outputFiles/`.

Un PDF qui échoue n'interrompt pas les autres : l'erreur est affichée dans la console.

## Limites

- Les PDF scannés (images sans texte) ne sont pas gérés : il faudrait un OCR.
- Détection des titres, des notes de bas de page et des en-têtes fondée sur des heuristiques (taille de police, gras, position, répétition) : à vérifier sur de nouveaux types de documents.
- Quelques mots coupés en fin de ligne peuvent subsister quand le mot entier n'apparaît nulle part ailleurs dans le document.
- Les PDF très graphiques (brochures en colonnes) donnent un résultat moins propre que les documents textuels.
