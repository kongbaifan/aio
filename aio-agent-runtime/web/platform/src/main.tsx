import { StrictMode, Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth';
import { Layout } from './components/Layout';
import { Loading } from './components/ui';
import { Home, Login } from './features/Home';
import { Conversation } from './features/Conversation';
import { Files, Approvals, UsagePage } from './features/WorkspacePages';
import './styles.css';

const AdminPage = lazy(() => import('./features/Admin').then((module) => ({ default: module.AdminPage })));
const ConnectionsPage = lazy(() =>
  import('./features/Connections').then((module) => ({ default: module.ConnectionsPage })),
);

const KnowledgePage = lazy(() =>
  import('./features/Knowledge').then((module) => ({ default: module.KnowledgePage })),
);
const KnowledgeDetailPage = lazy(() =>
  import('./features/Knowledge').then((module) => ({ default: module.KnowledgeDetailPage })),
);

function Application() {
  const { me, loading } = useAuth();
  if (loading)
    return (
      <div className="boot-screen">
        <span className="brand-symbol">
          a<span>i</span>o
        </span>
        <Loading label="正在验证企业身份…" />
      </div>
    );
  if (!me) return <Login />;
  return (
    <Routes>
      <Route element={<Layout key={`${me.org_id}:${me.user_id}`} />}>
        <Route path="/app" element={<Home />} />
        <Route path="/app/sessions/:sessionId" element={<Conversation />} />
        <Route path="/app/files" element={<Files />} />
        <Route path="/app/approvals" element={<Approvals />} />
        <Route path="/app/usage" element={<UsagePage />} />
        <Route
          path="/app/knowledge"
          element={
            <Suspense fallback={<Loading label="正在打开知识库…" />}>
              <KnowledgePage />
            </Suspense>
          }
        />
        <Route
          path="/app/knowledge/:knowledgeId"
          element={
            <Suspense fallback={<Loading label="正在读取获权文档…" />}>
              <KnowledgeDetailPage />
            </Suspense>
          }
        />
        <Route
          path="/app/connections"
          element={
            <Suspense fallback={<Loading label="正在打开连接管理…" />}>
              <ConnectionsPage />
            </Suspense>
          }
        />
        <Route
          path="/app/admin/:section?"
          element={
            <Suspense fallback={<Loading label="正在打开管理中心…" />}>
              <AdminPage />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/app" replace />} />
      </Route>
    </Routes>
  );
}
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Application />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
