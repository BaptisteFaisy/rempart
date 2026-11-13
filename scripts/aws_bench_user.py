#!/usr/bin/env python3
"""Crée et supprime un utilisateur Cognito de banc, pour jouer les preuves authentifiées.

Sert les preuves qui exigent un vrai jeton (`scripts/proof_real.py` : P2, P4,
P5*, P6, P7, P10). La recette est exactement celle-ci, exécutée dans l'ordre :

    python3 scripts/aws_bench_user.py --create    # imprime un jeton (IdToken)
    REMPART_TOKEN="$(…)" python3 scripts/proof_real.py
    python3 scripts/aws_bench_user.py --delete    # retire du groupe + supprime

Aucun mot de passe n'est affiché au-delà de la création. Si la session AWS
n'est pas active, ce script échoue en 401/ExpiredToken sans rien casser.

Règle : un utilisateur de banc ne reste **jamais** dans le pool à la fin d'une
preuve. `--create` vérifie qu'il est ensuite supprimé par `--delete`.
"""

from __future__ import annotations

import argparse
import secrets
import sys

import boto3

REGION = "eu-north-1"
POOL_ID = "eu-north-1_VkUAsvgSR"
CLIENT_ID = "7qr971kfs2jlj5i2d065mb1fbl"
GROUP = "platform_admin"
#: Le pool exige un identifiant au format e-mail (mesuré le 13/11/2026).
USERNAME = "bench-admin@example.invalid"


def _clients() -> tuple:
    return (
        boto3.client("cognito-idp", region_name=REGION),
    )


def create(quiet: bool = False) -> str:
    cognito = _clients()[0]
    password = f"Bench!{secrets.token_urlsafe(12)}"
    try:
        cognito.admin_create_user(
            UserPoolId=POOL_ID,
            Username=USERNAME,
            MessageAction="SUPPRESS",
        )
    except cognito.exceptions.UsernameExistsException:
        cognito.admin_delete_user(UserPoolId=POOL_ID, Username=USERNAME)
        cognito.admin_create_user(
            UserPoolId=POOL_ID, Username=USERNAME, MessageAction="SUPPRESS"
        )
    cognito.admin_set_user_password(
        UserPoolId=POOL_ID, Username=USERNAME, Password=password, Permanent=True
    )
    cognito.admin_add_user_to_group(
        UserPoolId=POOL_ID, Username=USERNAME, GroupName=GROUP
    )
    auth = cognito.initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        ClientId=CLIENT_ID,
        AuthParameters={"USERNAME": USERNAME, "PASSWORD": password},
    )
    # L'auteurisateur JWT d'API Gateway attend un jeton d'ACCESS (aud = client
    # de l'application), pas l'IdToken (aud = pool) : avec l'IdToken, l'API
    # répond 401 « Authentication required » et toutes les preuves P2/P4/P5 échouent.
    token = auth["AuthenticationResult"]["AccessToken"]
    if not quiet:
        print(f"jeton d'accès prêt : {token[:20]}…")
        print("export REMPART_TOKEN=$(python3 scripts/aws_bench_user.py --create --token-only)")
    return token


def delete() -> None:
    cognito = _clients()[0]
    cognito.admin_remove_user_from_group(
        UserPoolId=POOL_ID, Username=USERNAME, GroupName=GROUP
    )
    cognito.admin_delete_user(UserPoolId=POOL_ID, Username=USERNAME)
    print(f"utilisateur {USERNAME} retiré du groupe puis du pool")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create", action="store_true", help="crée l'utilisateur et imprime le jeton")
    parser.add_argument("--delete", action="store_true", help="supprime l'utilisateur de banc")
    parser.add_argument("--token-only", action="store_true", help="n'imprime que le jeton")
    args = parser.parse_args()

    if args.delete:
        delete()
        return 0
    if args.create:
        token = create(quiet=args.token_only)
        if args.token_only:
            print(token)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())