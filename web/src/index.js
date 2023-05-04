import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import './index.css';
import App from './App';

import 'bootstrap/dist/css/bootstrap.min.css';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
    <React.StrictMode>
        <BrowserRouter>
            <Routes>
                <Route path="/dashboard/:activeTab?/:activeComponent?" element={<App/>}/>
                <Route path="/dashboard/" element={<Navigate to='/dashboard/availability' />} />
            </Routes>
        </BrowserRouter>
    </React.StrictMode>
);
