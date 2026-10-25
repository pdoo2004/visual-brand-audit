import { z } from "zod";
import { ApiError } from "./errors";

/**
 * Shared request helper. Every endpoint function goes through `request`, so there is one
 * place that sends the call, validates the response, and turns failures into ApiError.
 *
 * The base path is relative: in development the Vite proxy forwards /api to the backend.
 */
const BASE_URL = "/api/v1";

export interface RequestOptions {
  method?: "GET" | "POST";
  /** JSON-serialisable body. Sent as application/json. */
  json?: unknown;
  /** Multipart body. The browser sets the Content-Type (with its boundary), so we must not. */
  formData?: FormData;
  /** Lets a screen cancel a request, for example when it unmounts mid-poll. */
  signal?: AbortSignal;
}

export async function request<S extends z.ZodType>(
  path: string,
  schema: S,
  options: RequestOptions = {},
): Promise<z.infer<S>> {
  const { method = "GET", json, formData, signal } = options;

  const init: RequestInit = { method, signal };
  if (formData) {
    init.body = formData;
  } else if (json !== undefined) {
    init.body = JSON.stringify(json);
    init.headers = { "Content-Type": "application/json" };
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch (err) {
    // A cancelled request is not a failure: let the caller's abort handling see it unchanged.
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "NETWORK_ERROR", "Could not reach the analysis service. Check that the API is running.");
  }

  if (!response.ok) throw await toApiError(response);

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(response.status, "INVALID_RESPONSE", "The service returned a response that was not valid JSON.");
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw new ApiError(
      response.status,
      "INVALID_RESPONSE",
      "The service returned data in an unexpected format.",
      parsed.error.issues,
    );
  }
  return parsed.data;
}

/** True for a plain object with a string `message`. */
function looksLikeErrorBody(value: unknown): value is { code?: unknown; message: string; details?: unknown } {
  return typeof value === "object" && value !== null && typeof (value as { message?: unknown }).message === "string";
}

/**
 * Reads an error response. The backend currently sends errors in three shapes:
 *   { error: { code, message, details } }   the contract's envelope
 *   { detail: { code, message, details } }  what FastAPI's HTTPException produces today
 *   { detail: [ { msg, loc, ... } ] }       FastAPI's own validation errors
 */
async function toApiError(response: Response): Promise<ApiError> {
  const fallback = `Request failed (${response.status}).`;
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return new ApiError(response.status, "UNKNOWN_ERROR", fallback);
  }

  const record = (typeof payload === "object" && payload !== null ? payload : {}) as Record<string, unknown>;
  const detail = record.detail as Record<string, unknown> | unknown[] | undefined;
  const candidates = [record.error, detail, !Array.isArray(detail) ? detail?.error : undefined];
  const body = candidates.find(looksLikeErrorBody);
  if (body) {
    return new ApiError(
      response.status,
      typeof body.code === "string" ? body.code : "UNKNOWN_ERROR",
      body.message,
      Array.isArray(body.details) ? body.details : [],
    );
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown };
    const message = typeof first?.msg === "string" ? first.msg : fallback;
    return new ApiError(response.status, "VALIDATION_ERROR", message, detail);
  }

  return new ApiError(response.status, "UNKNOWN_ERROR", fallback);
}