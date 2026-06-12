# NOTE: This file is auto-generated. Do not edit manually.

from typing import List, Optional

from pydantic import BaseModel, Field


class ExchangeRequest(BaseModel):
    public_key: Optional[str] = Field(alias="publicKey", default=None)
    model_config = dict(extra="forbid", populate_by_name=True)


class ExchangeResponse(BaseModel):
    exchange_id: str = Field(alias="exchangeId")
    encrypted_hashing_key: str = Field(alias="encryptedHashingKey")
    truveta_public_key: str = Field(alias="truvetaPublicKey")
    encrypted_rotation_iv: str = Field(alias="encryptedRotationIv")
    num_rotations: int = Field(alias="numRotations")
    bin_width: float = Field(alias="binWidth")
    dimension_bias: Optional[List[float]] = Field(alias="dimensionBias", default=None)
    model_config = dict(extra="forbid", populate_by_name=True)
