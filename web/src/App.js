import { useParams } from "react-router-dom";

import './App.css';

import Dashboard from './components/Dashboard.js'

function App() {
  const params = useParams();
  const activeTab = params.activeTab;
  const activeComponent = params.activeComponent;

  return (
    <div className="App">
        <Dashboard activeTab={activeTab} activeComponent={activeComponent}/>
    </div>
  );
}

export default App;
