import { useState, useEffect } from 'react';

export const useLocalStorage = (key, initialValue) => {
  const [storedValue, setStoredValue] = useState(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch (error) {
      console.error(`Error loading ${key} from localStorage:`, error);
      return initialValue;
    }
  });

  const setValue = (value) => {
    try {
      const valueToStore = value instanceof Function ? value(storedValue) : value;
      setStoredValue(valueToStore);
      window.localStorage.setItem(key, JSON.stringify(valueToStore));
    } catch (error) {
      console.error(`Error saving ${key} to localStorage:`, error);
    }
  };

  return [storedValue, setValue];
};

export const useDarkMode = () => {
  const [darkMode, setDarkMode] = useLocalStorage('darkMode', true);
  
  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
  };

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  return [darkMode, toggleDarkMode];
};

export const useChatMessages = () => {
  const [messages, setMessages] = useLocalStorage('chatMessages', []);
  
  const addMessage = (message) => {
    setMessages(prev => [...prev, message]);
  };

  const clearMessages = () => {
    setMessages([]);
    localStorage.removeItem('chatMessages');
  };

  return [messages, addMessage, clearMessages];
};

export const useCodeVersions = () => {
  const [codeVersions, setCodeVersions] = useLocalStorage('codeVersions', []);
  const [selectedVersion, setSelectedVersion] = useState(null);
  
  const addVersion = (version) => {
    setCodeVersions(prev => [...prev, version]);
    setSelectedVersion(version.id);
  };

  const loadVersion = (versionId) => {
    const version = codeVersions.find(v => v.id === versionId);
    if (version) {
      setSelectedVersion(versionId);
      return version;
    }
    return null;
  };

  const clearVersions = () => {
    setCodeVersions([]);
    setSelectedVersion(null);
    localStorage.removeItem('codeVersions');
  };

  return [codeVersions, selectedVersion, addVersion, loadVersion, clearVersions];
};
