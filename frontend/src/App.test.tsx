import { render, screen } from '@testing-library/react'

import App from './App'
import { Providers } from './app/providers'

describe('App', () => {
  it('renderiza o título da aplicação', () => {
    render(
      <Providers>
        <App />
      </Providers>,
    )
    expect(screen.getByRole('heading', { name: /hugecp threat intel/i })).toBeInTheDocument()
  })
})
