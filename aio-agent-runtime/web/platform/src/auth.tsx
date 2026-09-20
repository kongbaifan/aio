import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { api, ApiError, isAbort } from './api/client';
import type { Me } from './api/types';

interface AuthValue {
  me: Me | null;
  loading: boolean;
  error: string;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}
const AuthContext = createContext<AuthValue | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    setError('');
    try {
      const user = await api.request<Me>('/api/v2/me');
      api.bind(user);
      setMe(user);
    } catch (error) {
      if (isAbort(error)) return;
      setMe(null);
      if (!(error instanceof ApiError && error.status === 401)) setError('无法连接工作台，请稍后重试。');
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    const lost = () => {
      setMe(null);
      setLoading(false);
    };
    api.addEventListener('auth-lost', lost);
    void refresh();
    return () => api.removeEventListener('auth-lost', lost);
  }, [refresh]);
  const logout = useCallback(async () => {
    await api.request('/auth/logout', 'POST');
    api.invalidate();
    setMe(null);
  }, []);
  return (
    <AuthContext.Provider value={{ me, loading, error, refresh, logout }}>{children}</AuthContext.Provider>
  );
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('Missing AuthProvider');
  return value;
}
