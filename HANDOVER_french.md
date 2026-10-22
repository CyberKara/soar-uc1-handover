# UC1 — Automated Credential Rotation — Paquet de transfert (déploiement air-gapped)

Généré le 2026-10-22 23:45 UTC à partir de `credential_rotation` (environnement source : `soar8`).

Ce paquet est autonome — tout ce qu'il faut pour déployer ce cas d'usage manuellement
dans un environnement sans accès réseau vers ce dépôt ni vers `soar8`.

*(Version anglaise : `HANDOVER.md` dans ce même dossier.)*

## Contenu

| Chemin | Contenu |
|--------|---------|
| `connectors/` | Paquet(s) applicatif(s) connecteur : cyberark_ccp-v1.0.30.tgz |
| `connectors/source/` | Même(s) connecteur(s), extrait(s) — pour lecture, pas pour import |
| `custom_functions/` | Paquet(s) de fonctions personnalisées : cyberark_ccp_get_targets, cyberark_ccp_classify_secrets, cyberark_ccp_update_asset, cyberark_ccp_start_tests, cyberark_ccp_report |
| `custom_functions/source/` | Même(s) fonction(s) personnalisée(s), extraite(s) — pour lecture, pas pour import |
| `playbooks/` | Paquet(s) de playbooks : cyberark_credential_refresh |
| `playbooks/source/` | Même(s) playbook(s), extrait(s) — pour lecture, pas pour import |
| `assets/*.json` | Modèles de configuration d'assets (identifiants masqués — voir ci-dessous) |
| `custom_lists/*.json` | Liste(s) personnalisée(s) — les lignes définies par ce paquet, jamais les lignes de données de la source (voir la section dédiée ci-dessous) |
| `docs/` | Document de plan d'implémentation, pour le contexte de conception complet |

## [!] Mise à niveau d'une installation existante — à lire en premier

Ne concerne que le cas où cette application est déjà installée sur la cible
depuis un paquet précédent. Sur une cible vierge, passez à l'ordre
d'installation.

- **Connecteur 1.0.30, deux assets à rattacher et textes plus courts (2026-10-11).** Installez le connecteur v1.0.30 par-dessus l'app CyberArk CCP existante (même identifiant ; l'asset garde ses réglages). Réimportez les deux fonctions personnalisées et les trois playbooks. Le bloc `add_note_no_targets` de l'orchestrateur et le bloc `wait_before_recheck` du recheck handler utilisent désormais l'asset SOAR (Phantom) nommé `soar8` au lieu de `soar6` : rattachez ces deux blocs à votre propre asset SOAR dans le VPE et enregistrez, sinon la note « aucune cible » n'est jamais écrite et chaque nouvelle tentative échoue. `cyberark_recheck_handler` garde ses fonctions dans le Global Custom Code, donc un enregistrement dans le VPE ne le casse plus, et `cyberark_credential_rotation` continue d'envoyer le filtre CyberArk `address` après un enregistrement. Gardez l'orchestrateur et le recheck handler actifs, Run As votre utilisateur d'automatisation. Le plan d'implémentation dans `docs/` ne décrit plus que la conception actuelle, avec un Setup Guide (`INSTALL.md` est supprimé).

- **Un playbook remplace les trois (2026-10-22).** Désactivez puis supprimez `cyberark_rotation_orchestrator`, `cyberark_recheck_handler` et `cyberark_credential_rotation`, ainsi que les fonctions personnalisées `cyberark_asset_get_tagged_for_rotation` et `cyberark_asset_update_configuration`. Importez les cinq fonctions personnalisées `cyberark_ccp_*` (publiez-les) : la mise à jour n'écrit plus que le champ mot de passe (l'ancienne remplaçait tous les autres champs mot de passe de la cible par `********`), et une ligne de liste inutilisable est signalée. Importez `cyberark_credential_refresh` ; son bloc `start_tests` porte l'interrupteur `test_connectivity` (true). Créez un rôle qui copie Automation avec Assets : Edit autorisé, et un utilisateur d'automatisation avec ce rôle. Dans le VPE, réglez le Run As du playbook sur cet utilisateur (l'import ne le conserve pas), rattachez `get_secrets` et `wait_for_tests` à vos assets CyberArk CCP et SOAR, enregistrez, puis activez-le. La liste, le label et l'asset Timer ne changent pas ; les valeurs de statut ont changé (plan d'implémentation). Un APPAP282E est désormais retenté au prochain passage du Timer, et non plus après 5 minutes.

## Ordre d'installation

1. **Installer l'application/les applications connecteur** — Apps > Install App, charger
   chaque fichier de `connectors/`.
   (`connectors/source/` est le même code extrait pour lecture — ne pas importer depuis ce
   dossier, l'interface a besoin du `.tgz`.)
2. **Configurer les assets à partir des modèles dans `assets/`** — Apps > Configure New Asset
   pour chacun. Les champs listés dans le `redacted_fields` d'un modèle sont des espaces
   réservés (`<<SET ME...>>`) — **vous devez les renseigner vous-même** ; ils n'ont jamais
   été exportés avec des valeurs utilisables. Deux raisons distinctes apparaissent dans
   cette liste, et chaque espace réservé précise laquelle s'applique :

   - **Secrets** (mots de passe, clés d'API, certificats/clés) — à reprendre depuis votre
     propre coffre-fort (vault)/CMDB. SOAR chiffre les champs de type `password` au repos,
     le processus d'export ne peut donc pas les relire sous une forme utilisable, même en
     principe.
   - **Identités et adresses** (noms d'utilisateur, client/app id, URL des points de
     terminaison) — non secrètes, mais elles appartenaient à l'environnement source et
     n'ont aucun sens ici. Saisissez les valeurs attendues par *votre* système cible.
     **Une identité doit correspondre au justificatif saisi à côté d'elle** — un vrai mot
     de passe associé à un nom d'utilisateur résiduel de l'environnement source ne
     s'authentifie auprès de rien et renvoie une erreur HTTP 401.

   **Les playbooks sont livrés pointant vers les noms d'assets ci-dessous.** Créez vos
   assets avec ces noms, ou gardez vos propres noms et redirigez les blocs d'action de
   chaque playbook vers vos assets dans le VPE, puis enregistrez : chaque playbook de ce
   paquet est conçu pour résister à un enregistrement. (Un enregistrement rend un playbook
   lancé à la main disponible sur tous les libellés de conteneur ; le réimporter rétablit
   le libellé.)

   | Nom de l'asset | Application | Utilisé par | Modèle |
   |---|---|---|---|
   | `cyberark ccp mock` | CyberArk CCP | `cyberark_credential_refresh` | `assets/cyberark_ccp_mock.json` |
   | `soar8` | Phantom | `cyberark_credential_refresh` | `assets/soar8.json` |

3. **Créer la/les liste(s) personnalisée(s)** à partir de `custom_lists/*.json` — chaque
   fichier contient le tableau `content` exact (les lignes définies par ce paquet, jamais les lignes de données de la source) à
   envoyer en POST vers `/rest/decided_list` :
   ```bash
   curl -sk -u '<user>:<password>' -X POST https://<target>:<port>/rest/decided_list \
     -H 'Content-Type: application/json' \
     -d @custom_lists/<list_name>.json
   ```
   (la structure de premier niveau du fichier est `{"name": ..., "content": [...]}` —
   correspond directement au payload REST attendu.)
4. **Importer les fonctions personnalisées, puis les playbooks** (dans cet ordre — les
   playbooks référencent les CF). Chacun passe par son propre import :
   - **Fonctions personnalisées** — tous les `custom_functions/*.tgz` : dans l'onglet Custom
     Functions de la page Playbooks, le bouton d'envoi dont l'infobulle indique *Import Custom Function*.
     L'import de playbook refuse une archive de CF (« failed to identify the import as a
     playbook »). Si la CF apparaît ensuite en brouillon, ouvrez-la dans l'éditeur et
     enregistrez-la.
   - **Playbooks** — tous les `playbooks/*.tgz` : *Import Playbook* sur la page Playbooks.
   (`custom_functions/source/` et `playbooks/source/` sont le même code extrait pour lecture —
   ne pas importer depuis ces dossiers, l'interface a besoin du `.tgz`.)
5. **Activer les playbooks d'automatisation** (`cyberark_credential_refresh`) et définir leur utilisateur
   **Run As** selon le guide d'installation du document de plan d'implémentation
   (voir `docs/`).

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

1. **Test Connectivity** sur l'asset CyberArk CCP : il lit `test_safe` / `test_username` via CCP. Ajoutez ensuite une ligne à `cyberark_ccp_rotation_state` pour un asset de TEST, colonnes `asset`, `safe`, `user_field`, `pwd_field` et `address` remplies (le Data model du plan d'implémentation).

2. **Lancez-le :** Poll Now sur l'asset Timer `cyberark_ccp`, ou attendez son passage quotidien. Attendez-vous à un container de label `cyberark_ccp`, une exécution de `cyberark_credential_refresh` sous son utilisateur Run As, une note, et le `status` de la ligne à `success` (écrit, test connectivity réussi). `written (test failed)` : le mot de passe a été écrit mais le test de l'asset a échoué. `pending` : CyberArk a répondu APPAP282E, le passage suivant réessaie. `failed` donne le message de CyberArk, `Asset not found`, ou `not authorized to edit assets` (le rôle de l'utilisateur Run As n'a pas Assets : Edit).

Si rien ne se déclenche, vérifiez que le playbook est actif avec son Run As défini, puis `spawn.log`/`decided.log`/`actiond.log` sur l'hôte SOAR.

## Ce qui n'a volontairement PAS été exporté

- Les valeurs réelles des identifiants pour tout champ de configuration de type `password`
  (voir l'étape 2 ci-dessus).
- Les véritables assets cibles de rotation de l'environnement source — ce sont des assets de
  test spécifiques à ce labo, pas votre infrastructure. Suivez plutôt la section Amorçage
  ci-dessus.
- Tout ce qui n'est pas explicitement listé dans Contenu ci-dessus.
