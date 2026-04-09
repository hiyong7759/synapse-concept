import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { SessionsPage } from './pages/SessionsPage';
import { ChatPage } from './pages/ChatPage';
import { GraphPage } from './pages/GraphPage';
import { OnboardingPage } from './pages/OnboardingPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SessionsPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/chat/:sessionId" element={<ChatPage />} />
        <Route path="/chat" element={<Navigate to="/" replace />} />
        <Route path="/graph" element={<GraphPage />} />
      </Routes>
    </BrowserRouter>
  );
}
