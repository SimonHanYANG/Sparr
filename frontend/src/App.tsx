import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import Layout from './components/Layout'
import Applications from './pages/Applications'
import Auth from './pages/Auth'
import Home from './pages/Home'
import InterviewRoom from './pages/InterviewRoom'
import Jobs from './pages/Jobs'
import Profiling from './pages/Profiling'
import ResumeDetail from './pages/ResumeDetail'
import Resumes from './pages/Resumes'
import Settings from './pages/Settings'
import { useAuth } from './stores/auth'

function RequireAuth({ children }: { children: React.ReactElement }) {
  const loggedIn = useAuth((s) => s.loggedIn)
  const location = useLocation()
  if (!loggedIn) return <Navigate to="/login" state={{ from: location }} replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="login" element={<Auth mode="login" />} />
        <Route path="register" element={<Auth mode="register" />} />
        <Route
          path="resumes"
          element={
            <RequireAuth>
              <Resumes />
            </RequireAuth>
          }
        />
        <Route
          path="resumes/:id"
          element={
            <RequireAuth>
              <ResumeDetail />
            </RequireAuth>
          }
        />
        <Route
          path="profiling"
          element={
            <RequireAuth>
              <Profiling />
            </RequireAuth>
          }
        />
        <Route path="jobs" element={<Jobs />} />
        <Route
          path="applications"
          element={
            <RequireAuth>
              <Applications />
            </RequireAuth>
          }
        />
        <Route
          path="applications/:id"
          element={
            <RequireAuth>
              <InterviewRoom />
            </RequireAuth>
          }
        />
        <Route
          path="settings"
          element={
            <RequireAuth>
              <Settings />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
