# Stockage des pièces jointes

Le contenu binaire d'une pièce jointe est séparé de ses métadonnées. Les métadonnées
(nom, type, texte extrait, sections, `fichier_id`, `stockage`) restent dans la
collection Mongo `pieces` ; le contenu passe par un adapter de stockage.

Le port est `meridian.ports.stockage_pieces.StockagePieces`. Trois adapters sont
disponibles :

| `JUMEAU_PIECES_STORAGE` | Stockage | Configuration |
| --- | --- | --- |
| `mongo` (défaut) / `gridfs` | GridFS Mongo, bucket `pieces_fichiers` | `MONGO_URL`, `DB_NAME` |
| `local` | système de fichiers | `JUMEAU_PIECES_LOCAL_DIR` (défaut `var/pieces`) |
| `s3` | Amazon S3 ou compatible | `JUMEAU_PIECES_S3_BUCKET`, préfixe optionnel |
| `minio` | MinIO via API S3 | idem + endpoint obligatoire |

## Variables

```bash
# mode
JUMEAU_PIECES_STORAGE=local            # mongo | local | s3 | minio

# local
JUMEAU_PIECES_LOCAL_DIR=/var/lib/meridian/pieces

# s3 / minio
JUMEAU_PIECES_S3_BUCKET=meridian-pieces
JUMEAU_PIECES_S3_PREFIX=prod
JUMEAU_PIECES_S3_REGION=eu-west-3
JUMEAU_PIECES_S3_ENDPOINT=http://127.0.0.1:9000   # MinIO ; AWS_ENDPOINT_URL accepté
JUMEAU_PIECES_S3_FORCE_PATH_STYLE=1                # forcé en mode minio
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

En mode `s3`, boto3 utilise sa chaîne de credentials habituelle (variables, profil,
rôle IAM). En mode `minio`, l'endpoint et le path-style sont requis.

## MinIO local

```bash
docker run --rm -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minio -e MINIO_ROOT_PASSWORD=minio-secret \
  -v meridian-minio:/data minio/minio server /data --console-address ":9001"
```

Créer le bucket `meridian-pieces`, puis :

```bash
export JUMEAU_PIECES_STORAGE=minio
export JUMEAU_PIECES_S3_BUCKET=meridian-pieces
export JUMEAU_PIECES_S3_ENDPOINT=http://127.0.0.1:9000
export AWS_ACCESS_KEY_ID=minio
export AWS_SECRET_ACCESS_KEY=minio-secret
```

## Droits S3 minimaux

Pour un préfixe `prod/`, l'identité a besoin de :

```json
{
  "Effect": "Allow",
  "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
  "Resource": "arn:aws:s3:::meridian-pieces/prod/*"
}
```

Ajouter `s3:ListBucket` sur le bucket pour `--vider` (réinitialisation de démonstration).

## Compatibilité et bascule

Chaque nouvelle pièce enregistre `stockage` (`mongo`, `local`, `s3` ou `minio`) avec son
`fichier_id` :

* GridFS : identifiant ObjectId sérialisé ;
* local : chemin relatif à `JUMEAU_PIECES_LOCAL_DIR` ;
* S3/MinIO : clé complète `préfixe/case/pièce`.

Une pièce ancienne sans champ `stockage` est lue depuis Mongo : changer
`JUMEAU_PIECES_STORAGE` ne casse donc pas les pièces existantes. Les nouvelles pièces
vont dans le nouveau backend (stockage mixte). Pour migrer les anciens binaires, il faut
un outil de copie GridFS → cible qui réécrit `fichier_id` et `stockage` ; il n'est pas
fourni dans ce lot.

Le mode est validé au démarrage (`verifier_configuration_stockage`) : un bucket ou un
endpoint manquant fait échouer le boot plutôt que le premier upload.

## Sécurité

* Aucun bucket public ni URL présignée : le téléchargement passe par l'API authentifiée.
* Les clés locales sont confinées à `JUMEAU_PIECES_LOCAL_DIR` ; `..` et les chemins
  absolus sont refusés.
* Le nom d'origine reste une métadonnée ; il n'est jamais utilisé comme chemin.
* `X-Content-Type-Options: nosniff` et `Content-Disposition: attachment` restent posés
  par la route de téléchargement.
