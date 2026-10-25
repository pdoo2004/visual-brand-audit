import type { ApiErrorCode } from "./schemas";

/** Codes the client itself produces, in addition to the ones the backend sends. */
export type ClientErrorCode = "NETWORK_ERROR" | "INVALID_RESPONSE" | "UNKNOWN_ERROR";

/**
 * The one error type every API call throws. Screens catch this and show `message`;
 * they can branch on `code` (for example NOT_FOUND vs JOB_NOT_FINISHED) or `status`.
 */
export class ApiError extends Error {
  /** HTTP status, or 0 when no response was received. */
  readonly status: number;
  /** Backend code (VALIDATION_ERROR, NOT_FOUND, ...), a client code, or an unrecognised backend code. */
  readonly code: ApiErrorCode | ClientErrorCode | (string & {});
  readonly details: unknown[];

  constructor(
    status: number,
    code: ApiError["code"],
    message: string,
    details: unknown[] = [],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** Message to show a user for any thrown value. Never returns an empty string. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError || err instanceof Error) return err.message || "Something went wrong.";
  return "Something went wrong. Try again.";
}