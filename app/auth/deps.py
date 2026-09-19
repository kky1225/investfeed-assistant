from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.auth.jwks import JwksVerifier, Principal, TokenError


def get_verifier(request: Request) -> JwksVerifier:
    return request.app.state.verifier


def current_principal(request: Request, verifier: Annotated[JwksVerifier, Depends(get_verifier)]) -> Principal:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="bearer token required")
    try:
        return verifier.verify(auth[7:].strip())
    except TokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
