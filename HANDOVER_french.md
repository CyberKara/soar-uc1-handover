# UC1 — Automated Credential Rotation — Paquet de transfert (déploiement air-gapped)

Généré le 2026-08-06 21:29 UTC à partir de `credential_rotation` (environnement source : `soar8`).

Ce paquet est autonome — tout ce qu'il faut pour déployer ce cas d'usage manuellement
dans un environnement sans accès réseau vers ce dépôt ni vers `soar8`.

*(Version anglaise : `HANDOVER.md` dans ce même dossier.)*

## Contenu

| Chemin | Contenu |
|--------|---------|
| `connectors/` | Paquet(s) applicatif(s) connecteur : cyberark_ccp-v1.0.29.tgz |
| `connectors/source/` | Même(s) connecteur(s), extrait(s) — pour lecture, pas pour import |
| `playbooks/*.tgz` (CF) | cyberark_asset_update_configuration, cyberark_asset_get_tagged_for_rotation |
| `playbooks/*.tgz` (PB) | cyberark_credential_rotation, cyberark_rotation_orchestrator, cyberark_recheck_handler |
| `playbooks/source/` | Mêmes CF/playbooks, extraits — pour lecture, pas pour import |
| `assets/*.json` | Modèles de configuration d'assets (identifiants masqués — voir ci-dessous) |
| `custom_lists/*.json` | Schéma de la/les liste(s) personnalisée(s) (en-têtes uniquement — voir Amorçage ci-dessous) |
| `docs/` | Document de plan d'implémentation, pour le contexte de conception complet |

## Ordre d'installation

1. **Installer l'application/les applications connecteur** — Apps > Install App, charger
   chaque fichier de `connectors/`.
   (`connectors/source/` est le même code extrait pour lecture — ne pas importer depuis ce
   dossier, l'interface a besoin du `.tgz`.)
2. **Configurer les assets à partir des modèles dans `assets/`** — Apps > Configure New Asset
   pour chacun. Les champs listés dans le `redacted_fields` d'un modèle sont des espaces
   réservés (`<<SET ME...>>`) — **vous devez les renseigner vous-même** depuis votre propre
   coffre-fort (vault)/CMDB ; ils n'ont jamais été exportés avec de vraies valeurs (SOAR
   chiffre les champs de type `password` au repos et le processus d'export ne peut pas les
   relire sous une forme utilisable, même en principe).
3. **Créer la/les liste(s) personnalisée(s)** à partir de `custom_lists/*.json` — chaque
   fichier contient le tableau `content` exact (ligne d'en-tête + lignes de données) à
   envoyer en POST vers `/rest/decided_list` :
   ```bash
   curl -sk -u '<user>:<password>' -X POST https://<target>:<port>/rest/decided_list \
     -H 'Content-Type: application/json' \
     -d @custom_lists/<list_name>.json
   ```
   (la structure de premier niveau du fichier est `{"name": ..., "content": [...]}` —
   correspond directement au payload REST attendu.)
4. **Importer les fonctions personnalisées, puis les playbooks** (dans cet ordre — les
   playbooks référencent les CF) depuis `playbooks/*.tgz`, via Apps/Playbooks > Import dans
   l'interface SOAR cible.
   (`playbooks/source/` est le même code extrait pour lecture — ne pas importer depuis
   ce dossier, l'interface a besoin du `.tgz`.)
5. **Activer les playbooks d'automatisation** et définir leur utilisateur **Run As** selon
   le guide d'installation du document de plan d'implémentation (voir `docs/`).

## Amorçage du mapping vers le coffre-fort (découverte pilotée par la liste personnalisée)

La découverte de ce qui doit être traité est entièrement pilotée par le contenu de la liste
personnalisée que vous venez de créer — il n'y a **aucune étape de découverte automatique**.
Une nouvelle cible ne devient visible qu'une fois qu'une ligne lui est ajoutée. C'est
volontaire : faire correspondre un asset SOAR à son nom de coffre/compte dans le vault
nécessite une connaissance que vous seul possédez (quels assets ont besoin d'un identifiant
issu du vault, et comment cet identifiant est nommé dans votre vault) — rien dans SOAR ni
dans le vault ne peut déduire cela automatiquement.

Pour chaque asset que vous voulez que ce cas d'usage gère, ajoutez une ligne à la liste
personnalisée concernée en renseignant au moins ses colonnes de configuration (les colonnes
de statut/résultat peuvent rester vides — les playbooks les rempliront après la première
exécution réelle).

**Référence des colonnes** (les fichiers exportés `custom_lists/*.json` ne contiennent que
la ligne d'en-tête — volontairement aucune ligne de données, car les lignes de cet
environnement source sont ses propres assets de labo/test, pas les vôtres) :

- `cyberark_ccp_rotation_state` : `asset, safe, user_field, pwd_field, address, connector, username, status, message, last_rotated, event_link`
  - Ligne d'exemple (illustrative uniquement — remplacez chaque valeur) : `<nom-de-votre-asset>, <exemple-safe>, <exemple-user_field>, <exemple-pwd_field>, <exemple-address>, <exemple-connector>, <exemple-username>, <exemple-status>, <exemple-message>, <exemple-last_rotated>, <exemple-event_link>`

Consultez le document de plan d'implémentation copié dans `docs/` pour la sémantique exacte
des colonnes.

## Vérification

Une fois tout importé et les playbooks d'automatisation activés, déclenchez une exécution
manuelle (par ex. le poll manuel de l'asset Timer, ou selon la section de déclenchement du
document de plan d'implémentation)
et vérifiez : qu'un container est créé, que le(s)
playbook(s) enfant(s) attendu(s) s'exécute(nt), et que la/les liste(s) personnalisée(s)
reflète(nt) un résultat réel. Consultez `spawn.log`/`decided.log`/`actiond.log` sur l'hôte
SOAR cible si quelque chose ne se déclenche pas comme prévu.

## Ce qui n'a volontairement PAS été exporté

- Les valeurs réelles des identifiants pour tout champ de configuration de type `password`
  (voir l'étape 2 ci-dessus).
- Les véritables assets cibles de rotation de l'environnement source — ce sont des assets de
  test spécifiques à ce labo, pas votre infrastructure. Suivez plutôt la section Amorçage
  ci-dessus.
- Tout ce qui n'est pas explicitement listé dans Contenu ci-dessus.
