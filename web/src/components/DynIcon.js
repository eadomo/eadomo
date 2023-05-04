import * as icons from 'react-bootstrap-icons';

interface IconProps extends icons.IconProps {
  iconName: str
}

export const Icon = ({ iconName, ...props }: IconProps) => {
  const BootstrapIcon = icons[iconName];
  return <BootstrapIcon {...props} />;
}
