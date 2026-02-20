import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { installUnauthorizedResponseInterceptor } from './utils/fetchInterceptor'

installUnauthorizedResponseInterceptor()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
