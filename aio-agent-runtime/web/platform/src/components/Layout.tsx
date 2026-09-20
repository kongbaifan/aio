import { createContext, useContext, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  Bot,
  ChevronRight,
  Files,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  Plus,
  Settings2,
  ShieldCheck,
  Wallet,
  Cable,
  LibraryBig,
  X,
} from 'lucide-react';
import { useAuth } from '../auth';
import { useResource } from '../hooks';
import { explain } from '../api/client';
import type { Page, Project, Session } from '../api/types';
import { ErrorBox } from './ui';

interface WorkspaceValue {
  projects: Project[];
  sessions: Session[];
  refresh: () => void;
}
const WorkspaceContext = createContext<WorkspaceValue | null>(null);
export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('Missing workspace');
  return ctx;
}
export function Layout() {
  const { me, logout } = useAuth();
  const location = useLocation();
  const [mobile, setMobile] = useState(false);
  const [error, setError] = useState('');
  const projects = useResource<Page<Project>>('/api/v2/projects');
  const sessions = useResource<Page<Session>>('/api/v2/sessions');
  if (!me) return null;
  const title = location.pathname.startsWith('/app/admin')
    ? '组织管理'
    : location.pathname.startsWith('/app/files')
      ? '项目文件'
      : location.pathname.startsWith('/app/approvals')
        ? '待办审批'
        : location.pathname.startsWith('/app/usage')
          ? '我的用量'
          : '工作台';
  return (
    <WorkspaceContext.Provider
      value={{
        projects: projects.data?.items ?? [],
        sessions: sessions.data?.items ?? [],
        refresh: () => {
          projects.reload();
          sessions.reload();
        },
      }}
    >
      <div className="app-shell">
        <a className="skip-link" href="#main-content">
          跳到主要内容
        </a>
        {mobile && (
          <button className="sidebar-scrim" aria-label="关闭导航" onClick={() => setMobile(false)} />
        )}
        <aside className={`sidebar ${mobile ? 'is-open' : ''}`}>
          <Link className="brand" to="/app" onClick={() => setMobile(false)}>
            <span className="brand-symbol" aria-hidden="true">
              a<span>i</span>o
            </span>
            <div>
              <strong>共同工作台</strong>
              <small>ENTERPRISE AGENTS</small>
            </div>
          </Link>
          <button className="mobile-close icon-button" aria-label="关闭导航" onClick={() => setMobile(false)}>
            <X size={18} />
          </button>
          <Link className="new-session" to="/app" onClick={() => setMobile(false)}>
            <Plus size={17} />
            发起新任务
          </Link>
          <nav aria-label="主要导航">
            <NavLink to="/app" end onClick={() => setMobile(false)}>
              <LayoutDashboard size={17} />
              工作台
            </NavLink>
            <NavLink to="/app/files" onClick={() => setMobile(false)}>
              <Files size={17} />
              项目文件
            </NavLink>
            <NavLink to="/app/approvals" onClick={() => setMobile(false)}>
              <ShieldCheck size={17} />
              待办审批
            </NavLink>
            <NavLink to="/app/usage" onClick={() => setMobile(false)}>
              <Wallet size={17} />
              我的用量
            </NavLink>
            {me.capabilities.mcp && (
              <NavLink to="/app/connections" onClick={() => setMobile(false)}>
                <Cable size={17} />
                我的连接
              </NavLink>
            )}
            {me.capabilities.knowledge && (
              <NavLink to="/app/knowledge" onClick={() => setMobile(false)}>
                <LibraryBig size={17} />
                知识库
              </NavLink>
            )}
          </nav>
          <div className="sidebar-section">
            <span>我的对话</span>
            <span>{sessions.data?.items.length ?? '—'}</span>
          </div>
          <div className="session-list">
            {sessions.loading ? (
              <p className="sidebar-note">读取中…</p>
            ) : sessions.data?.items.length ? (
              sessions.data.items.slice(0, 20).map((session) => (
                <NavLink
                  key={session.id}
                  to={`/app/sessions/${session.id}`}
                  onClick={() => setMobile(false)}
                  className="session-link"
                >
                  <MessageSquare size={14} />
                  <span>{session.title}</span>
                </NavLink>
              ))
            ) : (
              <p className="sidebar-note">开始任务后，对话会保存在这里。</p>
            )}
            {sessions.error && (
              <button className="sidebar-note" onClick={sessions.reload}>
                读取失败，点击重试
              </button>
            )}
          </div>
          <div className="sidebar-bottom">
            {(me.permissions.organization_admin || me.permissions.operations || me.permissions.audit) && (
              <NavLink to="/app/admin" onClick={() => setMobile(false)} className="admin-nav">
                <Settings2 size={17} />
                管理中心
                <ChevronRight size={14} />
              </NavLink>
            )}
            <div className="account">
              <span className="avatar">{me.display_name.slice(0, 1)}</span>
              <div>
                <strong>{me.display_name}</strong>
                <small>
                  {me.departments.map((d) => d.name).join(' · ') ||
                    (me.role === 'org_admin' ? '组织管理员' : '组织成员')}
                </small>
              </div>
              <button
                className="icon-button"
                aria-label="退出登录"
                onClick={() => void logout().catch((e) => setError(explain(e)))}
              >
                <LogOut size={16} />
              </button>
            </div>
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <button className="mobile-menu icon-button" aria-label="打开导航" onClick={() => setMobile(true)}>
              <Menu size={20} />
            </button>
            <div className="breadcrumb">
              <span>{me.organization_name}</span>
              <ChevronRight size={13} />
              <strong>{title}</strong>
            </div>
            <div className="topbar-status">
              <span className="status-dot" />
              <span>企业身份已验证</span>
            </div>
          </header>
          <main id="main-content" className="main-content">
            <ErrorBox message={error || projects.error} />
            <Outlet />
          </main>
          <footer className="app-footer">
            <Bot size={13} />
            <span>AI 结果请结合业务依据核对。你的任务权限由组织策略决定。</span>
          </footer>
        </div>
      </div>
    </WorkspaceContext.Provider>
  );
}
