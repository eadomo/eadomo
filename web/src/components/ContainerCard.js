import React, { useState, useRef, useEffect } from 'react';
import Table from 'react-bootstrap/Table';
import Card from 'react-bootstrap/Card';
import Button from 'react-bootstrap/Button';
import Modal from 'react-bootstrap/Modal';
import Tooltip from 'react-bootstrap/Tooltip';
import Alert from 'react-bootstrap/Alert';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import * as Icon from 'react-bootstrap-icons';
import axios from 'axios';
import * as CardFuncs from './CardFuncs.js'
import getBackendUrlBase from './backendUrl.js'

export default function ContainerCard(props) {
    const [container, ] = useState(props.container);
    const [focus, ] = useState(props.focus);
    const [containerForRestart, setContainerForRestart] = useState(null)
    const adminMode = props.adminMode

    const myRef = useRef(null);

    useEffect(() => {
        if (focus)
            myRef.current.scrollIntoView();
    });

    const showDesc = (
        <Tooltip id="objectDesc">{container.desc ? container.desc : "no description"}</Tooltip>
    )

    const restartContainer = (container) => {
        const backendUrl = getBackendUrlBase() + 'container/'
            + container.name + '/restart'

        axios
          .get(backendUrl)
          .then(response =>
            console.log(response)
          )
          .catch(e => console.log(e));
    }

    return (
        <Card ref={myRef} border="primary" className="shadow p-3 mb-5 bg-white rounded">
          <Card.Body>
            <Card.Title>
                <div className="toolbar-bar">
                <div className="led-container toolbar-el">
                    <div className={CardFuncs.getContainerLEDStyle(container)}></div>
                </div>
                <OverlayTrigger placement="top" overlay={showDesc}>
                    <div className="cardtitle me-auto text-start toolbar-el" style={{paddingRight: "5px"}}>
                        {container.friendlyName}
                    </div>
                </OverlayTrigger>
                { container.update_available && <div className="toolbar-el">
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipUpdateAvailable}><Icon.CloudDownload style={{color:"#00FF00"}}/></OverlayTrigger>
                    </div>
                }
                { container.src_update_available && <div className="toolbar-el">
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipSrcUpdateAvailable}><Icon.Lightning style={{color:"#00FF00"}}/></OverlayTrigger>
                    </div>
                }
                <div className="vr" style={{ verticalAlign:"bottom", marginLeft: "1px", marginRight: "4px" }}/>
                <div className="toolbar-el"><span style={{cursor:"pointer"}} onClick={() => props.showContainerLogs(container)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipShowLog}><Icon.Tv/></OverlayTrigger>
                    </span>
                </div>
                <div className="toolbar-el"><span style={{cursor:"pointer"}} onClick={() => props.showContainerStatusTimeseries(container)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipAvailGraph}><Icon.BarChart/></OverlayTrigger>
                    </span>
                </div>
                { container.panel &&
                <div className="toolbar-el"><span style={{cursor:"pointer"}} onClick={() => CardFuncs.openLink(container.panel)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipOpenLink}><Icon.BoxArrowUp/></OverlayTrigger>
                    </span>
                </div>
                }
                { container.src &&
                <div className="toolbar-el"><span style={{cursor:"pointer"}} onClick={() => CardFuncs.openLink(container.src)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipOpenLinkToSourceCode}><Icon.CardHeading/></OverlayTrigger>
                    </span>
                </div>
                }
                { adminMode &&
                <div className="toolbar-el"><span style={{cursor:"pointer"}} onClick={() => props.showContainerEnvVars(container)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipShowEnvs}><Icon.WalletFill style={{color:"red"}}/></OverlayTrigger>
                    </span>
                </div>
                }
                { adminMode &&
                <div className="toolbar-el"><span style={{cursor:"pointer"}} onClick={() => props.showContainerInspect(container)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipShowInspect}><Icon.ZoomIn style={{color:"red"}}/></OverlayTrigger>
                    </span>
                </div>
                }
                { adminMode &&
                <div className="toolbar-el"><span style={{cursor:"pointer"}} onClick={() => props.showImageInspect(container)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipShowImageInspect}><Icon.Binoculars style={{color:"red"}}/></OverlayTrigger>
                    </span>
                </div>
                }
                { adminMode &&
                <div className="toolbar-el"><span style={{cursor:"pointer"}} onClick={() => setContainerForRestart(container)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipRestartCont}><Icon.ArrowClockwise style={{color:"red"}}/></OverlayTrigger>
                    </span>
                </div>
                }
                </div>
            </Card.Title>
            { container.stats && Object.keys(container.stats).length > 0 &&
                <Table className="statstable">
                <tbody>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsUptime}><Icon.Clock/></OverlayTrigger></td><td>{CardFuncs.formatSeconds(container.stats?.uptime_seconds)}</td>
                    <td><span style={{cursor:"pointer"}} onClick={() => props.showContainerPlot(container, 'uptime_seconds', 'Uptime [s]')}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsCPU}><Icon.Cpu/></OverlayTrigger></td><td>{CardFuncs.formatPercentage(container.stats?.cpu_usage_percent)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showContainerPlot(container, 'cpu_usage_percent', 'CPU usage [%]')}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsRAM}><Icon.Memory/></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.memory_usage_bytes)} / {CardFuncs.formatBytes(container.stats?.memory_available_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showContainerPlot(container, 'memory_usage_bytes', 'Memory usage [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipNumPids}><Icon.Grid/></OverlayTrigger></td><td>{container.stats?.pids}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showContainerPlot(container, 'pids', 'PIDs')}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                {
                    container.stats?.disk_usage.map((mp, index) =>
                        <tr key={'stats-disk'+index}><td><OverlayTrigger placement="right" overlay={<Tooltip id="tooltipStatsDisk">Disk usage of {mp.mount_point}</Tooltip>}><Icon.DeviceHdd/></OverlayTrigger></td><td>{CardFuncs.formatPercentage(mp.usage_percentage)}</td>
                        <td><span style={{cursor:"pointer"}}  onClick={() => props.showContainerPlot(container, 'disk_usage', 'Disk space usage [%]', x => x[index].usage_percentage)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td></tr>
                    )
                }
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsDiskRead}><span><Icon.DeviceHdd/> <Icon.CloudArrowDown/></span></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.blkio_read_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showContainerPlot(container, 'blkio_read_bytes', 'disk read [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsDiskWriten}><span><Icon.DeviceHdd/>  <Icon.CloudArrowUp/></span></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.blkio_written_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showContainerPlot(container, 'blkio_written_bytes', 'disk written [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsNetworkRcvd}><span><Icon.Wifi/> <Icon.CloudArrowDown/></span></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.network_received_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showContainerPlot(container, 'network_received_bytes', 'network received [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsNetworkSent}><span><Icon.Wifi/> <Icon.CloudArrowUp/></span></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.network_sent_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showContainerPlot(container, 'network_sent_bytes', 'network sent [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                </tbody>
                </Table>
               }
          </Card.Body>
          <Modal
              show={containerForRestart != null}
              centered
              onHide={() => setContainerForRestart(null)}
            >
              <Modal.Body><Alert variant="danger">Please confirm that you really want to restart container {containerForRestart?.name}</Alert></Modal.Body>
              <Modal.Footer>
                <Button
                  variant="secondary"
                  onClick={() => setContainerForRestart(null)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  onClick={() => { restartContainer(containerForRestart); setContainerForRestart(null); } }>
                  OK
                </Button>
              </Modal.Footer>
          </Modal>
        </Card>
        )
}