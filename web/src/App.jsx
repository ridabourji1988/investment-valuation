import { useEffect, useState } from 'react'
import { api } from './lib/api'
import Feed from './components/Feed'
import Asset from './components/Asset'
import Macro from './components/Macro'
import Learn from './components/Learn'

export default function App() {
  const [tab, setTab] = useState('feed')
  const [asset, setAsset] = useState(null)
  const [formulas, setFormulas] = useState(null)

  useEffect(() => {
    // Formula registry powers the "Show Calculation" sheets everywhere.
    api.formulas().then((d) => {
      const map = {}
      d.formulas.forEach((f) => { map[f.formula_id] = f })
      setFormulas(map)
    }).catch(() => {})
  }, [])

  const navItems = [['feed', 'Feed'], ['macro', 'Macro & Cycle'], ['learn', 'Learn']]
  return (
    <div className="app">
      <nav className="topnav">
        <span style={{ fontWeight: 800, fontSize: 16, marginRight: 12 }}>ValueScope</span>
        {navItems.map(([id, label]) => (
          <span key={id} className={'item ' + (tab === id ? 'sel' : '')}
            onClick={() => setTab(id)}>{label}</span>
        ))}
      </nav>
      {tab === 'feed' && <Feed onOpen={setAsset} onMacro={() => setTab('macro')} />}
      {tab === 'macro' && <Macro formulas={formulas} />}
      {tab === 'learn' && <Learn />}

      {asset && <Asset ticker={asset} formulas={formulas} onClose={() => setAsset(null)} />}

      <nav className="tabbar">
        <div className={'item ' + (tab === 'feed' ? 'sel' : '')} onClick={() => setTab('feed')}>
          <span className="ic">◎</span>Feed
        </div>
        <div className={'item ' + (tab === 'macro' ? 'sel' : '')} onClick={() => setTab('macro')}>
          <span className="ic">◔</span>Macro
        </div>
        <div className={'item ' + (tab === 'learn' ? 'sel' : '')} onClick={() => setTab('learn')}>
          <span className="ic">✎</span>Learn
        </div>
      </nav>
    </div>
  )
}
