import { Layout, Button } from 'antd';
import { useNavigate } from 'react-router-dom';

export default function Error() {
    const navigate = useNavigate();

    return (
        <Layout
            style={{
                width: '100%',
                height: '100vh', // 使用 100vh 让它占满整个视口高度
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
            }}
        >
            <h4 style={{ fontSize: '1.5rem' }}>Ops, nothing here.</h4>
            <Button style={{ color: 'fff' }} type="primary" onClick={() => navigate('/dashboard')}>
                返回
            </Button>
        </Layout>
    );
}