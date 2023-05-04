import React, { useState, useRef, useEffect } from 'react';
import Table from 'react-bootstrap/Table';
import Stack from 'react-bootstrap/Stack';
import Card from 'react-bootstrap/Card';
import Tooltip from 'react-bootstrap/Tooltip';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import * as Icon from 'react-bootstrap-icons';
import * as CardFuncs from './CardFuncs.js'

export default function ServiceCard(props) {
    const [container, ] = useState(props.service);
    const [focus, ] = useState(props.focus);

    const myRef = useRef(null);

    useEffect(() => {
        if (focus)
            myRef.current.scrollIntoView();
    });

    const showDesc = (
        <Tooltip id="objectDesc">{container.desc ? container.desc : "no description"}</Tooltip>
    )

    return (
        <Card ref={myRef} border="primary" className="shadow p-3 mb-5 bg-white rounded">
          <Card.Body>
            <Card.Title>
                <Stack direction="horizontal" gap={3}>
                <div className="led-container ">
                    <div className={CardFuncs.getContainerLEDStyle(container)}></div>
                </div>
                <OverlayTrigger placement="top" overlay={showDesc}>
                    <div className="cardtitle me-auto text-start">
                        {container.friendlyName}
                    </div>
                </OverlayTrigger>
                { container.src_update_available && <div>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipSrcUpdateAvailable}><Icon.Lightning style={{color:"#00FF00"}}/></OverlayTrigger>
                    </div>
                }
                <div className="vr" />
                <div><span style={{cursor:"pointer"}} onClick={() => props.showServiceStatusTimeseries(container)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipAvailGraph}><Icon.BarChart/></OverlayTrigger>
                    </span>
                </div>
                { container.panel &&
                <div><span style={{cursor:"pointer"}} onClick={() => CardFuncs.openLink(container.panel)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipOpenLink}><Icon.ArrowBarUp/></OverlayTrigger>
                    </span>
                </div>
                }
                { container.src &&
                <div><span style={{cursor:"pointer"}} onClick={() => CardFuncs.openLink(container.src)}>
                    <OverlayTrigger placement="top" overlay={CardFuncs.tooltipOpenLinkToSourceCode}><Icon.CardHeading/></OverlayTrigger>
                    </span>
                </div>
                }
                </Stack>
            </Card.Title>
            { container.stats && Object.keys(container.stats).length > 0 &&
                <Table className="statstable">
                <tbody>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsUptime}><Icon.Clock/></OverlayTrigger></td><td>{CardFuncs.formatSeconds(container.stats?.uptime_seconds)}</td>
                    <td><span style={{cursor:"pointer"}} onClick={() => props.showServicePlot(container, 'uptime_seconds', 'Uptime [s]')}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsCPU}><Icon.Cpu/></OverlayTrigger></td><td>{CardFuncs.formatPercentage(container.stats?.cpu_usage_percent)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showServicePlot(container, 'cpu_usage_percent', 'CPU usage [%]')}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsRAM}><Icon.Memory/></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.memory_usage_bytes)} / {CardFuncs.formatBytes(container.stats?.memory_available_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showServicePlot(container, 'memory_usage_bytes', 'Memory usage [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipNumPids}><Icon.Grid/></OverlayTrigger></td><td>{container.stats?.pids}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showServicePlot(container, 'pids', 'PIDs')}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                {
                    container.stats?.disk_usage?.map((mp, index) =>
                        <tr key={'stats-disk'+index}><td><OverlayTrigger placement="right" overlay={<Tooltip id="tooltipStatsDisk">Disk usage of {mp.mount_point}</Tooltip>}><Icon.DeviceHdd/></OverlayTrigger></td><td>{CardFuncs.formatPercentage(mp.usage_percentage)}</td>
                        <td><span style={{cursor:"pointer"}}  onClick={() => props.showServicePlot(container, 'disk_usage', 'Disk space usage [%]', x => x[index].usage_percentage)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td></tr>
                    )
                }
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsDiskRead}><span><Icon.DeviceHdd/> <Icon.CloudArrowDown/></span></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.blkio_read_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showServicePlot(container, 'blkio_read_bytes', 'disk read [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsDiskWriten}><span><Icon.DeviceHdd/>  <Icon.CloudArrowUp/></span></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.blkio_written_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showServicePlot(container, 'blkio_written_bytes', 'disk written [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsNetworkRcvd}><span><Icon.Wifi/> <Icon.CloudArrowDown/></span></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.network_received_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showServicePlot(container, 'network_received_bytes', 'network received [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                <tr>
                    <td><OverlayTrigger placement="right" overlay={CardFuncs.tooltipStatsNetworkSent}><span><Icon.Wifi/> <Icon.CloudArrowUp/></span></OverlayTrigger></td><td>{CardFuncs.formatBytes(container.stats?.network_sent_bytes)}</td>
                    <td><span style={{cursor:"pointer"}}  onClick={() => props.showServicePlot(container, 'network_sent_bytes', 'network sent [MB]', x => x/1024/1024)}><OverlayTrigger placement="left" overlay={CardFuncs.tooltipTimeseries}><Icon.GraphUp/></OverlayTrigger></span></td>
                </tr>
                </tbody>
                </Table>
              }
          </Card.Body>
        </Card>
    )
}