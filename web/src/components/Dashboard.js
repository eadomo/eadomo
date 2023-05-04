import React, { useState, useEffect, useCallback } from 'react';
import useAxios from "axios-hooks";
import axios from 'axios';
import Card from 'react-bootstrap/Card';
import Container from 'react-bootstrap/Container';
import Stack from 'react-bootstrap/Stack';
import Row from 'react-bootstrap/Row';
import Col from 'react-bootstrap/Col';
import Table from 'react-bootstrap/Table';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Tab from 'react-bootstrap/Tab';
import Alert from 'react-bootstrap/Alert';
import Tooltip from 'react-bootstrap/Tooltip';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Form from 'react-bootstrap/Form';
import Tabs from 'react-bootstrap/Tabs';import 'moment-timezone';
import moment from 'moment';
import Moment from 'react-moment';
import { useNavigate } from "react-router-dom";
import * as Icon from 'react-bootstrap-icons';

import ContainerCard from './ContainerCard.js'
import JmxCard from './JmxCard.js'
import DockerCard from './DockerCard.js'
import ServiceCard from './ServiceCard.js'
import TimeseriesPlot from './TimeseriesPlot.js'
import LogWindow from './LogWindow.js'
import EnvVarsWindow from './EnvVarsWindow.js'
import InspectContainerWindow from './InspectContainerWindow.js'
import InspectImageWindow from './InspectImageWindow.js'
import UptimeGraph from './UptimeGraph.js'
import ActionWindow from './ActionWindow.js'
import RunTaskWindow from './RunTaskWindow.js'
import { Icon as DynIcon } from './DynIcon.js'
import ErrorMessage from './ErrorMessage.js'
import getBackendUrlBase from './backendUrl.js'

export default function Dashboard(props) {
    const navigate = useNavigate();

    const [activeTab, setActiveTab] = useState(props.activeTab);
    const [activeComponent, setActiveComponent] = useState(props.activeComponent);

    if (!activeTab) {
        window.history.pushState({}, undefined, "/dashboard/availability");
        setActiveTab("availability")
    }

    const [plotModalVisible, setPlotModalVisible] = useState(false);
    const [logModalVisible, setLogModalVisible] = useState(false);
    const [formUsername, setFormUsername] = useState(null);
    const [formPassword, setFormPassword] = useState(null);
    const [envModalVisible, setEnvModalVisible] = useState(false);
    const [contInspectModalVisible, setContInspectModalVisible] = useState(false);
    const [imageInspectModalVisible, setImageInspectModalVisible] = useState(false);
    const [actModalVisible, setActModalVisible] = useState(false);
    const [taskModalVisible, setTaskModalVisible] = useState(false);
    const [taskUrl, setTaskUrl] = useState(null);
    const [taskTitle, setTaskTitle] = useState(null);
    const [loginModalVisible, setLoginModalVisible] = useState(false);
    const [statusTimeseriesModalVisible, setStatusTimeseriesModalVisible] = useState(false);
    const [selectedContainer, setSelectedContainer] = useState(null);
    const [selectedAction, setSelectedAction] = useState(null);
    const [plottedParameter, setPlottedParameter] = useState(null);
    const [plotName, setPlotName] = useState(null);
    const [plotSourceType, setPlotSourceType] = useState(null);
    const [convFunc, setConvFunc] = useState(null);

    const transformStatus = (status) => {
        const name = status.name;
        const containers = Object.entries(status.containers).map(([key, value]) => ({
            name: key,
            ...value
        }));
        const services = Object.entries(status.services).map(([key, value]) => ({
            name: key,
            ...value
        }));
        const jmx = Object.entries(status.jmx).map(([key, value]) => ({
            name: key,
            ...value
        }));
        for (const x of containers) {
            x.friendlyName = x['friendly-name'] ? x['friendly-name'] : x.name
        }
        for (const x of services) {
            x.friendlyName = x['friendly-name'] ? x['friendly-name'] : x.name
        }
        for (const x of jmx) {
            x.friendlyName = x['friendly-name'] ? x['friendly-name'] : x.name
        }
        return {
            updatedAt: moment(),
            name: name,
            containers: containers,
            services: services,
            jmx: jmx
        }
    }

    const backendUrl = getBackendUrlBase()

    const backendUrlStatus = backendUrl + 'status'
    const [{ data: dataStatus1, loading: loadingStatus, error: errorStatus }, refetchStatus] = useAxios(backendUrlStatus)

    const dataStatus = dataStatus1 ? transformStatus(dataStatus1) : null

    const backendUrlAdminModeEnabled = backendUrl + 'admin-mode'
    const [{ data: adminModeEnabledStr }, refetchAdminMode] = useAxios({url: backendUrlAdminModeEnabled, withCredentials: true})

    const backendUrlActionsEnabled = backendUrl + 'actions-enabled'
    const [{ data: actionsEnabledStr }, refetchActionsEnabled] = useAxios({url: backendUrlActionsEnabled, withCredentials: true})

    const adminModeEnabled = adminModeEnabledStr === true
    const actionsEnabled = actionsEnabledStr === true

    const refetchAll = useCallback(() => {
        refetchStatus();
        refetchAdminMode();
        refetchActionsEnabled();
    }, [refetchStatus, refetchAdminMode, refetchActionsEnabled])

    const forceUpdate = useCallback(() => {
        refetchAll();
    }, [refetchAll])

    useEffect(() => {
        const interval = setInterval(() => {
          forceUpdate();
        }, 30000);
        return () => clearInterval(interval);
    }, [forceUpdate])

    const backendUrlLog = backendUrl + 'log'
    const [{ data:log, loading:loadingLog, error:errorLog }] =
        useAxios({url: backendUrlLog, withCredentials: true})

    const backendUrlSchedInt = backendUrl + 'restart-notifications'
    const [{ data:schedInt, loading:loadingSchedInt, error:errorSchedInt }] =
        useAxios({url: backendUrlSchedInt, withCredentials: true})

    const backendUrlActions = backendUrl + 'get-actions'
    const [{ data:actions, loading:loadingActions, error:errorActions }] =
        useAxios({url: backendUrlActions, withCredentials: true})

    const backendUrlDockerIds = backendUrl + 'docker/ids'
    const [{ data:dockerIds, loading:loadingDockerIds, error:errorDockerIds }] =
        useAxios({url: backendUrlDockerIds, withCredentials: true})

    const backendUrlReadme = backendUrl + 'get-readme'
    const [{ data: dataReadme, loading: loadingReadme, error: errorReadme }] =
        useAxios({url: backendUrlReadme, withCredentials: true})

    const backendUrlVersion = backendUrl + 'version'
    const [{ data: serverVersion }] =
        useAxios({url: backendUrlVersion})

    const getEntryColor = (entry) => {
        if (entry.severity === 'alarm')
            return 'red';
        if (entry.severity === 'warning')
            return 'yellow';
        else
            return 'var(--bs-table-striped-color)'
    }

    const runAction = (action) => {
        setActModalVisible(true);
        setSelectedAction(action);
    }

    const runTask = (url, title) => {
        console.log("running task", url, title);
        setTaskModalVisible(true);
        setTaskUrl(url);
        setTaskTitle(title);
    }

    const handleTabClick = (tabKey) => {
        navigate("/dashboard/" + tabKey);
        setActiveComponent(null);
        setActiveTab(tabKey);
    }

    const login = (event) => {
        event.preventDefault();
        setLoginModalVisible(false);

        const formData = new FormData();
        formData.append('username', formUsername);
        formData.append('password', formPassword);

        const backendUrlLogin = backendUrl + 'login';

        axios.post(backendUrlLogin, formData,
            { "Content-Type": "multipart/form-data", withCredentials: true }
        )
        .then(x => forceUpdate())
        .catch(e => console.log("error", e))
    }

    const logout = () => {
        const backendUrlLogout = backendUrl + 'logout';

        axios.get(backendUrlLogout, { withCredentials: true })
        .then(x => forceUpdate())
        .catch(e => console.log("error", e))
    }

    function History()  {
        if (loadingLog) return "loading...";
        if (errorLog) return <ErrorMessage message={errorLog.message}/>;

        return <div className="logtable shadow p-3 mb-5 bg-white rounded square border rounded-3 border-primary">
            <Table size="sm" striped hover>
                <tbody>
                {
                    log.map(entry =>
                        <tr key={'log'+entry.timestamp}>
                            <td><Moment format="YYYY-MM-DD HH:mm">{entry.timestamp}</Moment></td>
                            <td style={{ color: getEntryColor(entry) }}>{entry.severity}</td>
                            <td className="w-75" align="left">{entry.message}</td>
                        </tr>
                    )
                }
                </tbody>
            </Table></div>
    }

    function ScheduledInterruptions()  {
        if (loadingSchedInt) return "loading...";
        if (errorSchedInt) return <ErrorMessage message={errorSchedInt.message}/>;

        return <div className="schedinttable shadow p-3 mb-5 bg-white rounded square border rounded-3 border-primary">
            <Table size="sm" striped hover>
                <thead>
                    <tr><td>Issued</td><td>Object</td><td>From</td><td>Until</td><td>When</td></tr>
                </thead>
                <tbody>
                {
                    schedInt.map(entry =>
                        <tr key={'log'+entry.creation_time}>
                            <td><Moment format="YYYY-MM-DD HH:mm">{entry.creation_time}</Moment></td>
                            <td>{entry.object_type}: {entry.affected_object}</td>
                            <td><Moment format="YYYY-MM-DD HH:mm">{entry.valid_from}</Moment></td>
                            <td><Moment format="YYYY-MM-DD HH:mm">{entry.valid_until}</Moment></td>
                            <td><Moment date={entry.valid_from} fromNow/></td>
                            <td>{entry.message}</td>
                        </tr>
                    )
                }
                </tbody>
            </Table></div>
    }

    function Actions() {
        if (loadingActions) return "loading...";
        if (errorActions) return <ErrorMessage message={errorActions.message}/>;
        return <Row xs={1} md={3}>
            {
                actions.map(action => <Col key={action.id}><Card><Button onClick={() => runAction(action)} variant="outline-primary"><DynIcon iconName={action.icon}/> {action.name}</Button></Card></Col>)
            }
            </Row>
    }

    function DockerActions() {
        if (loadingDockerIds) return "loading...";
        if (errorDockerIds) return <ErrorMessage message={errorDockerIds.message}/>;

        return <Row xs={1} md={3}>
            {
                dockerIds.map(dockerId =>
                      <Col key={dockerId}>
                            <DockerCard key={dockerId} dockerId={dockerId} runTask={runTask}/>
                      </Col>
                )
            }
            </Row>
    }

    function ReadMe() {
        if (loadingReadme) return "loading...";
        if (errorReadme) return <ErrorMessage message={errorReadme.message}/>;
        if (dataReadme)
            return <div className="text-start fs-4"><pre>{dataReadme}</pre></div>
        else
            return <div>No README provided</div>
    }

    function About() {
        const serverVersionText = serverVersion ? serverVersion.version : '-';
        const serverCommitText = serverVersion ? serverVersion.commit : '-';
        const apiVersionText = serverVersion ? serverVersion.api_version : '-';
        return <div>
            <h3>EaDoMo - Easy Docker Monitoring</h3>
            <div>EaDoMo is a tool which allows you to monitor your docker deployments in an easy way</div>
            <div style={{fontSize: 12}}>UI version: {process.env.REACT_APP_VERSION}-{process.env.REACT_APP_COMMIT_ID ?? 'unknown'}</div>
            <div style={{fontSize: 12}}>server version: {serverVersionText}-{serverCommitText}</div>
            <div style={{fontSize: 12}}>API version: {apiVersionText}</div>
            </div>
    }

    function Jmx() {
        if (!dataStatus && loadingStatus) return "loading..."
        if (errorStatus || !dataStatus) return <ErrorMessage message={errorStatus.message}/>
        return <Row xs={1} md={3}>
            {
                dataStatus.jmx
                .map(container =>
                      <Col key={container.name}>
                        <JmxCard showJmxPlot={showJmxPlot}
                            showJmxUserDefinedPlot={showJmxUserDefinedPlot}
                            showJmxStatusTimeseries={showJmxStatusTimeseries}
                            focus={activeComponent && (container.name === activeComponent)}
                            container={container}/>
                      </Col>
                )
            }
            </Row>
    }

    function Containers() {
        if (!dataStatus && loadingStatus) return "loading..."
        if (errorStatus || !dataStatus) return <ErrorMessage message={errorStatus.message}/>
        return <Row xs={1} md={3}>
            {
                dataStatus.containers
                .map(container =>
                      <Col key={container.name}>
                        <ContainerCard
                            showContainerLogs={showContainerLogs}
                            showContainerEnvVars={showContainerEnvVars}
                            showContainerInspect={showContainerInspect}
                            showImageInspect={showImageInspect}
                            showContainerPlot={showContainerPlot}
                            showContainerStatusTimeseries={showContainerStatusTimeseries}
                            container={container}
                            adminMode={adminModeEnabled}
                            focus={activeComponent && (container.name === activeComponent)}/>
                      </Col>
                )
            }
            </Row>
    }

    function Services() {
        if (!dataStatus && loadingStatus) return "loading..."
        if (errorStatus || !dataStatus) return <ErrorMessage message={errorStatus.message}/>
        return <Row xs={1} md={3}>
            {
                dataStatus.services
                .map(service =>
                      <Col key={service.name}>
                        <ServiceCard
                            showServiceStatusTimeseries={showServiceStatusTimeseries}
                            showServicePlot={showServicePlot}
                            focus={activeComponent && (service.name === activeComponent)}
                            service={service}/>
                      </Col>
                )
            }
            </Row>
    }

    const showContainerStatusTimeseries = (container) => {
        setPlotSourceType('container');
        setSelectedContainer(container);
        setStatusTimeseriesModalVisible(true);
    }

    const showContainerPlot = (container, param, plotName, convFunc) => {
        setPlotSourceType('container');
        setConvFunc((x) => convFunc);
        setPlotName(plotName);
        setPlottedParameter(param);
        setSelectedContainer(container);
        setPlotModalVisible(true);
    }

    const showServicePlot = (service, param, plotName, convFunc) => {
        setPlotSourceType('service');
        setConvFunc((x) => convFunc);
        setPlotName(plotName);
        setPlottedParameter(param);
        setSelectedContainer(service);
        setPlotModalVisible(true);
    }

    const showContainerLogs = (container) => {
        setSelectedContainer(container);
        setLogModalVisible(true);
    }

    const showContainerEnvVars = (container) => {
        setSelectedContainer(container);
        setEnvModalVisible(true);
    }

    const showContainerInspect = (container) => {
        setSelectedContainer(container);
        setContInspectModalVisible(true);
    }

    const showImageInspect = (container) => {
        setSelectedContainer(container);
        setImageInspectModalVisible(true);
    }

    const showJmxPlot = (container, param, plotName, convFunc) => {
        setPlotSourceType('jmx');
        setConvFunc((x) => convFunc);
        setPlotName(plotName);
        setPlottedParameter(param);
        setSelectedContainer(container);
        setPlotModalVisible(true);
    }

    const showJmxUserDefinedPlot = (container, param, plotName, convFunc) => {
        setPlotSourceType('jmx/user_defined');
        setConvFunc((x) => convFunc);
        setPlotName(plotName);
        setPlottedParameter(param);
        setSelectedContainer(container);
        setPlotModalVisible(true);
    }

    const showJmxStatusTimeseries = (container) => {
        setPlotSourceType('jmx');
        setSelectedContainer(container);
        setStatusTimeseriesModalVisible(true);
    }

    const showServiceStatusTimeseries = (service) => {
        setPlotSourceType('service');
        setSelectedContainer(service);
        setStatusTimeseriesModalVisible(true);
    }

    const tooltipLogin = (
      <Tooltip id="tooltipLogin">Login</Tooltip>
    )

    const tooltipLogout = (
      <Tooltip id="tooltipLogout">Logout</Tooltip>
    )

    return (
    <div>
      <Modal show={loginModalVisible} centered onHide={() => setLoginModalVisible(false)} className="modal-lg">
        <Form onSubmit={login}>
        <Modal.Header closeButton>
            <Modal.Title>Login</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <Form.Group className="mb-3" controlId="formUsername">
            <Form.Label>Username</Form.Label>
            <Form.Control type="text" onChange={e => setFormUsername(e.target.value)} placeholder="Enter username" />
          </Form.Group>

          <Form.Group className="mb-3" controlId="formPassword">
            <Form.Label>Password</Form.Label>
            <Form.Control type="password" onChange={e => setFormPassword(e.target.value)} placeholder="Password" />
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="primary" type="submit">
            OK
          </Button>
          <Button variant="secondary" onClick={() => setLoginModalVisible(false)}>
            Close
          </Button>
        </Modal.Footer>
        </Form>
      </Modal>
      <Modal show={actModalVisible} centered onHide={() => setActModalVisible(false)} className="modal-lg">
        <Modal.Header closeButton>
            <Modal.Title>{selectedAction?.name}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
            { selectedAction && actModalVisible &&
                <ActionWindow action={selectedAction}/>
            }
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setActModalVisible(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
      <Modal show={taskModalVisible} centered onHide={() => setTaskModalVisible(false)} className="modal-lg">
        <Modal.Header closeButton>
            <Modal.Title>{taskTitle}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
            { taskUrl && taskModalVisible &&
                <RunTaskWindow url={taskUrl}/>
            }
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setTaskModalVisible(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
      <Modal show={plotModalVisible} centered onHide={() => setPlotModalVisible(false)} className="modal-lg">
        <Modal.Header closeButton/>
        <Modal.Body>
            { selectedContainer && plotModalVisible &&
            <TimeseriesPlot
                container={selectedContainer?.name}
                parameter={plottedParameter}
                plotName={plotName}
                convFunc={convFunc}
                type={plotSourceType}
                />
            }
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setPlotModalVisible(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
      <Modal show={logModalVisible} centered onHide={() => setLogModalVisible(false)} className="modal-xl">
        <Modal.Header closeButton>
            <Modal.Title>{selectedContainer?.friendlyName}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
            { selectedContainer && logModalVisible &&
            <LogWindow container={selectedContainer?.name}/>
            }
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setLogModalVisible(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
      <Modal show={envModalVisible} centered onHide={() => setEnvModalVisible(false)} className="modal-lg">
        <Modal.Header closeButton>
            <Modal.Title>{selectedContainer?.friendlyName}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
            { selectedContainer && envModalVisible &&
            <EnvVarsWindow container={selectedContainer?.name}/>
            }
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setEnvModalVisible(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
      <Modal show={contInspectModalVisible} centered onHide={() => setContInspectModalVisible(false)} className="modal-lg">
        <Modal.Header closeButton>
            <Modal.Title>Inspecting container <b>{selectedContainer?.friendlyName}</b></Modal.Title>
        </Modal.Header>
        <Modal.Body>
            { selectedContainer && contInspectModalVisible &&
            <InspectContainerWindow container={selectedContainer?.name}/>
            }
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setContInspectModalVisible(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
      <Modal show={imageInspectModalVisible} centered onHide={() => setImageInspectModalVisible(false)} className="modal-lg">
        <Modal.Header closeButton>
            <Modal.Title>Inspecting image of container <b>{selectedContainer?.friendlyName}</b></Modal.Title>
        </Modal.Header>
        <Modal.Body>
            { selectedContainer && imageInspectModalVisible &&
            <InspectImageWindow container={selectedContainer?.name}/>
            }
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setImageInspectModalVisible(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
      <Modal show={statusTimeseriesModalVisible} centered onHide={() => setStatusTimeseriesModalVisible(false)} className="modal-lg">
        <Modal.Header closeButton/>
        <Modal.Body>
            {selectedContainer && statusTimeseriesModalVisible &&
                <UptimeGraph
                    container={selectedContainer?.name}
                    type={plotSourceType}/>
            }
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setStatusTimeseriesModalVisible(false)}>
            Close
          </Button>
        </Modal.Footer>
      </Modal>
      <Container fluid>
          <Stack gap={3}>
                <Stack direction="horizontal">
                <h1 style={{width:"100%"}}>{dataStatus?.name}</h1>
                <div>
                    { !adminModeEnabled && <OverlayTrigger placement="left" overlay={tooltipLogin}><Icon.DoorClosed style={{cursor:"pointer"}} onClick={setLoginModalVisible}/></OverlayTrigger> }
                    { adminModeEnabled && <OverlayTrigger placement="left" overlay={tooltipLogout}><Icon.ArrowBarRight style={{cursor:"pointer"}} onClick={logout}/></OverlayTrigger> }
                </div>
                </Stack>
                { adminModeEnabled && <Alert variant="danger">ADMIN MODE</Alert>}
                  <Tabs
                  defaultActiveKey="availability"
                  id="tab"
                  activeKey={activeTab}
                  onSelect={handleTabClick}
                  mountOnEnter={true}
                  unmountOnExit={true}
                  className="mb-3">
                    <Tab eventKey="availability" title="Availability">
                        <UptimeGraph/>
                    </Tab>
                    <Tab eventKey="containers" title="Containers">
                        <Containers/>
                    </Tab>
                    <Tab eventKey="services" title="Services">
                      <Services/>
                    </Tab>
                    <Tab eventKey="jmx" title="JMX">
                      <Jmx/>
                    </Tab>
                    { actionsEnabled &&
                    <Tab eventKey="actions" title="Actions">
                      <Actions/>
                    </Tab>
                    }
                    { adminModeEnabled &&
                    <Tab eventKey="dockerActions" title="Docker actions">
                      <DockerActions/>
                    </Tab>
                    }
                    <Tab eventKey="history" title="History">
                      <History/>
                    </Tab>
                    <Tab eventKey="schedint" title="Scheduled interruptions">
                      <ScheduledInterruptions/>
                    </Tab>
                    <Tab eventKey="readme" title="Read me">
                      <ReadMe/>
                    </Tab>
                    <Tab eventKey="about" title="About">
                      <About/>
                    </Tab>
                </Tabs>
                { dataStatus?.updatedAt != null &&
                <p className="text-left" style={{fontSize: 10}}>Last updated: <Moment>{dataStatus.updatedAt}</Moment></p>
                }
          </Stack>
      </Container>
      </div>
    )
}