import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';

export default function AuthGateway({ children }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAccounts = async () => {
      try {
        // Use correct API endpoint: /api/v1/client/accounts
        const res = await api.get('/v1/client/accounts');
        // If we have at least one REAL connected account
        if (res.data && res.data.length > 0) {
          // If the user is currently on the setup page, move them to client dashboard
          if (window.location.pathname === '/onboarding/setup') {
            navigate('/client');
          }
        } else {
          // If no accounts, force them to setup (unless they are already there)
          if (window.location.pathname !== '/onboarding/setup') {
            navigate('/onboarding/setup');
          }
        }
      } catch (err) {
        console.error("Auth check failed", err);
        // On error, allow access but log the issue
      } finally {
        setLoading(false);
      }
    };

    checkAccounts();
  }, [navigate]);

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  return children;
}
