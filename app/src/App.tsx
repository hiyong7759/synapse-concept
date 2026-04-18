import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ExplorerPage } from './pages/ExplorerPage';
import { ChatPage } from './pages/ChatPage';
import { GraphPage } from './pages/GraphPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { ReviewPage } from './pages/ReviewPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ExplorerPage />} />
        <Route path="/explore" element={<ExplorerPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
        <Route path="/chat/new" element={<ChatPage />} />
        <Route path="/chat" element={<Navigate to="/chat/new" replace />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/review" element={<ReviewPage />} />
      </Routes>
    </BrowserRouter>
  );
}
