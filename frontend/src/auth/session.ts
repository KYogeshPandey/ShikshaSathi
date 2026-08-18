export interface AuthSessionStore {
  getAccessToken(): string | null;
  setAccessToken(token: string): void;
  clearAccessToken(): void;
  invalidate(): void;
}

type UnauthorizedHandler = () => void;

export class MemoryAuthSession implements AuthSessionStore {
  private accessToken: string | null = null;
  private unauthorizedHandler: UnauthorizedHandler | null = null;

  getAccessToken(): string | null {
    return this.accessToken;
  }

  setAccessToken(token: string): void {
    this.accessToken = token;
  }

  clearAccessToken(): void {
    this.accessToken = null;
  }

  invalidate(): void {
    const hadSession = this.accessToken !== null;
    this.clearAccessToken();
    if (hadSession) {
      this.unauthorizedHandler?.();
    }
  }

  setUnauthorizedHandler(handler: UnauthorizedHandler): () => void {
    this.unauthorizedHandler = handler;
    return () => {
      if (this.unauthorizedHandler === handler) {
        this.unauthorizedHandler = null;
      }
    };
  }
}

export const authSession = new MemoryAuthSession();
