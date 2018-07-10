"""
Author: Francisco Javier Guzman

Last edited: 20/feb/18


Ranch wrapper

Usage
=====

>>> prot = Ranch(dom1, linker1, dom2, linker2, ..., chains = {dom1:'chainA',
               dom2:'chainC'}, symmetry='p2', symtemplate=dom2)


"""

## DELETE SELF. VARIABLES? (E.G. SELF.DOMS_IN)

import biskit as B
import numpy as N
import tempfile, os
import re
from operator import itemgetter
from biskit.core import oldnumeric as N0

from biskit.exe.executor import Executor
import biskit.tools as t

class Ranch( Executor ):


   chains = {}
   pdbs_in = ()
   sequence = ''


   def __init__(self, *domains, chains={}, symmetry='p1', symtemplate=None, 
      overall_sym='mixed', fixed=None, multich=None, debug=False):
      
      """
      

      """

      # Raise exception if symmetry is different than p1 and symtemplate is 
      # None, and if symtemplate is not in domains
      
      # Create temporary folder for pdbs and sequence
      tempdir = tempfile.mkdtemp( '', self.__class__.__name__.lower() + '_', 
         t.tempDir() )

      # Create temporary folder for models
      self.dir_models = tempfile.mkdtemp( '', 'models_', tempdir )

      self.f_seq = tempdir + '/sequence.seq'

      self.domains = domains
      self.chains = chains
      self.sequence = ''
      self.symmetry = symmetry
      self.symtemplate = symtemplate
      self.doms_in = []    # list of domains as PDBModels
      self.pdbs_in = []    # list of pdb file paths
      self.fixed = fixed
      self.multich = multich
      self.embedded = {}   # dictionary with domain : residue number to
                           # identify and locate embedded domains

      overall_symmetry = {
         'mixed' : 'm',
         'symmetry' : 's',
         'asymmetry' : 'a',
      }

      self.overall_sym = overall_symmetry[overall_sym]

      if self.fixed == None:
         self.fixed = []
         for element in self.domains:
            if isinstance(element, B.PDBModel):
               self.fixed.append('no')

      if self.multich == None:
         self.multich = []
         for element in self.domains:
            if isinstance(element, B.PDBModel):
               if element == self.symtemplate:
                  self.multich.append('yes')
               else:
                  self.multich.append('no')

      self._setup()

      Executor.__init__(self, 'ranch', tempdir=tempdir, cwd=tempdir, debug=debug)


   def _setup(self):
      """
      - Creates the sequence from the domains and linkers
      - Creates new PDBModels for ranch input if necessary (which are later
         converted into pdb files by prepare method)
      """
      
      ######## DIAGRAM STARTS ########

      ## The numbers are a reference to the steps in multiprot/doc

      i = 0   # Counter for domain position
      for element in self.domains:
         
         if isinstance(element, str):    # 1
            # If is sequence, add to sequence and continue
            self.sequence += element
            continue

         elif isinstance(element, B.PDBModel):
            # if is PDBModel

            if self.multich[i]=='yes' or element.lenChains()==1 or \
            self.fixed[i] == 'yes':
               # If is symmetry core or a single chain-domain ... 2
               # Or is a domain already modeled/fixed ... 3

               # For multiple chains with symmetry, the symetric unit should 
               # already be embedded in the (modified) symtemplate

               # THE HIGHER LEVEL PROGRAM MUST GIVE THE ENTIRE MODEL WITH
               # MULTIPLE CHAINS EMBEDDED IN ONE OF THE FIXED DOMAINS, AND
               # IT WILL BE TREATED AS A SINGLE CHAIN-DOMAIN, TO AVOID STEPS 
               # 4 AND 5 IN DIAGRAM
               # IT ALSO HAS TO REMOVE THE BOUND DOMAINS THAT WILL BE
               # MODELED IN OTHER CHAINS, TO AVOID STEP 6

               # Find a way to make the symmetry test only once?
               
               # Action: Add to sequence and to domains list
               # Conserve fixing
               
               self.sequence += element.sequence()
               self.doms_in.append(element)

            else:
               # Not modeled, but paired with another domain

               if isinstance(self.chains[element], (list, tuple)):   # 7
                  # if the other part of the domain is bound to the
                  # same chain, the chains entry of the domain will
                  # have a tuple with the chains to be taken, in order

                  # Action: Embed sequence of paired domain into
                  # element. Take the sequence and domains up to this
                  # point and model. Change coordinates, fix both
                  # domains and separate as individual fixed domains. 
                  # Go back to before adding the first dom,
                  # proceed as normal

                  # Be careful to put the separate domains in the correct order, 
                  # consulting self.chains[element]

                  # Can only work in the higher level implementation

                  # 8
                  # Get chain index
                  chain_id = self.chains[element][0]
                  # Gets True values only for the specified chain index
                  mask_chain = element.maskFrom('chain_id', chain_id)
                  # Convert True values to indices
                  i_mask_chain = N.nonzero(mask_chain)[0]
                  chain_ind = element.atom2chainIndices(i_mask_chain)[0]

                  m = element.takeChains([chain_ind])
                  m_emb = Ranch.embed(m, element)

                  self.embedded[m] = len(self.sequence) + 2

                  self.sequence += m_emb.sequence()
                  self.doms_in.append(m_emb)

                  break

               else: 
                  # Only one domain from element is part of the chain
                  # Action: Embed the paired domains into the selected chain

                  # 9
                  # Get chain index
                  chain_id = self.chains[element]
                  mask_chain = element.maskFrom('chain_id', chain_id)
                  i_mask_chain = N.nonzero(mask_chain)[0]
                  chain_ind = element.atom2chainIndices(i_mask_chain)[0]

                  m = element.takeChains([chain_ind])
                  m_emb = Ranch.embed(m, element)
                  
                  self.embedded[m] = len(self.sequence) + 2

                  self.sequence += m_emb.sequence()
                  self.doms_in.append(m_emb)

      ####### DIAGRAM FINISHES... REACHED STEP 9 #########

         else:
            raise TypeError(
               'The *domains arguments must be either strings or PDBModels.')

         i += 1

      return None


   @classmethod
   def embed(cls, dom, int_dom):
      '''
      Embeds one model (int_dom - possibly with multiple chains) into another 
      (dom) to trick ranch to treat them as a simple single-chain domain

      :param dom: model of a single chain domain that will contain the
                  other model
      :type dom: PDBModel
      :param int_dom: model of a single or multiple chain domain that will be 
                   embedded into 'dom'
      :type int_dom: PDBModel
      '''

      # See if the part to embed contains dom, and remove it if it does

      start = dom.sequence()[:10]

      if re.search(start, int_dom.sequence()):
         # If the dom sequence is inside int_dom sequence
         # Action: look for the position of dom inside int_dom, and extract

         matches = re.finditer(start, int_dom.sequence())
         first_res_dom = dom.res2atomIndices([0])
         lowdom = first_res_dom[0]
         highdom = first_res_dom[-1]

         for match in matches:
            index = match.start()
            first_res_int = int_dom.res2atomIndices([index])

            lowint = first_res_int[0]
            highint = first_res_int[-1]

            if N.all(dom.xyz[lowdom:highdom+1] == int_dom.xyz[lowint:highint+1]):
               # If the atoms for the first residue are in the same positions
               # Action: extract chain

               int_dom = Ranch.extract_fixed(dom, int_dom)

               break

      first = dom.take(dom.res2atomIndices([0,1]))
      last = dom.take(dom.res2atomIndices(list(range(2,dom.lenResidues()))))

      return first.concat(int_dom,last)
      

   ## Make class method?
   @classmethod
   def extract_fixed(cls, dom, full):
      """
      Extracts one model from another
      Finds the position of 'dom' inside 'full' comparing the sequence and atom
      coordinates for each chain in dom, gets the chain index and takes all the
      chains but the ones selected.
      
      :param dom: model of a single or multiple chain domain
      :type dom: PDBModel
      :param full: model of a multiple chain domain that contains 'dom'
      :type full: PDBModel

      :return: model 'full' without dom
      :type return: PDBModel
      """

      chains_to_take = list(range(full.lenChains()))

      # Make a list with one PDBModel for each chain in dom
      # This is to find one chain from dom at a time, in case they are not
      # together in 'full' ... is this even necessary?
      doms = [dom.takeChains([i]) for i in range(dom.lenChains())]

      for m in doms:

         start = m.sequence()[:10]  # could use the entire sequence instead
         
         if re.search(start, full.sequence()):
            # If the m sequence is inside full sequence
            # Action: look for the position of m inside full, and extract

            matches = re.finditer(start, full.sequence())
            first_res_m = m.res2atomIndices([0])
            lowm = first_res_m[0]
            highm = first_res_m[-1]
            
            for match in matches:
               index = match.start()
               first_res_full = full.res2atomIndices([index])

               lowfull = first_res_full[0]
               highfull = first_res_full[-1]

               if N.all(m.xyz[lowm:highm+1] == full.xyz[lowfull:highfull+1]):
                  # If the atoms for the first residue are in the same positions
                  # Action: remove chain index from chains_to_take
                  chain_ind = full.atom2chainIndices(first_res_full)
                  chains_to_take.remove(chain_ind[0])
                  break

      full = full.takeChains(chains_to_take)

      return full

   ## make class method?
   @classmethod
   def extract_embedded(cls, full, embedded):
      """
      Extracts one  or more PDBModels from another
      Finds the sequence and location of each domain in embedded dictionary.
      Extracts the atoms and concatenates at the end of 'self'. 
      Renumbers amino acids, id number and renames chains in the process.
      
      :param embedded: dictionary with embedded domains and its position (index)
                        in the full sequence
      :type embedded: dictionary

      :return: 'self' with embedded domains concatenated at the end as independent chains
      :type return: PDBModel
      """

      ## For the higher level program, add an argument to provide the dictionary

      chains_to_take = list(range(full.lenChains()))

      r = B.PDBModel()
      emb_ind = []   # List for start and end indexes for each embedded domain

      for dom, i_start in embedded.items():
         
         i_end = i_start + len(dom.sequence())

         if full.sequence()[i_start:i_end] == dom.sequence():
            r = r.concat(full.takeResidues(list(range(i_start, i_end))))
            emb_ind.append((i_start, i_end))
         else:
            raise TypeError('Problem with the embedded sequence/index')

      # Sort the list to remove the atoms from highest to lowest index,
      # so the indexes won't be affected
      emb_ind = sorted(emb_ind, key=itemgetter(0), reverse=True)

      for i_start, i_end in emb_ind:
         atomi_start = full.resIndex()[i_start]
         atomi_end = full.resIndex()[i_end]
         full.remove(list(range(atomi_start, atomi_end)))

      # Concat the original chain that previously contained the embedded domains
      for i in range(full.lenChains()-1):
         full.mergeChains(0)

      full.renumberResidues()    # Renumber amino acids
      full = full.concat(r)      # Combine full and r
      full.addChainId()          # Add chain IDs with consecutive letters
                                 # NOTE: add feature for personalized chain names

      # Renumber atoms
      full['serial_number'] = N0.arange(1,len(full)+1)

      return full


   def prepare(self):
      """
      Overrides Executor method.
      """
      # Create tempdir for pdbs and seq.... it is already created
      Executor.prepare(self)

      # Write pdb files
      for i in range(len(self.doms_in)):
         pdb_name = self.tempdir + '/' + str(i) + '_'
         if self.doms_in[i].validSource() == None:
            pdb_name += '.pdb'
         else:
            pdb_name += self.doms_in[i].sourceFile()[-8:]

         self.pdbs_in.append(pdb_name)
         self.doms_in[i].writePdb(pdb_name)

      # Write sequence file
      with open(self.f_seq, 'w') as f:
         f.write(self.sequence)

      # Generate by default 10 models, with no intensities
      self.args = self.f_seq + ' -q=10 -i'

      self.args = self.args + ' -s=%s -y=%s' % (self.symmetry, self.overall_sym)

      self.args = self.args + ' -x=%s' * len(self.pdbs_in) % tuple(self.pdbs_in)

      self.args = self.args + ' -f=%s' * len(self.fixed) % tuple(self.fixed)

      self.args = self.args + ' -o=%s' * len(self.multich) % tuple(self.multich)

      self.args = self.args + ' -w=%s' % self.dir_models

      
   def isFailed(self):
      """
      Overrides executor method
      """
      ## CHECK HOW TO SEE OUTPUT

      return self.error or 'Problems' in str(self.output)

   def fail(self):
      """
      Overrides Executor method. Called when execution fails.
      """

      ## CHECK IF THE MESSAGE POPS UP

      print('Ranch call failed.')   ## temporary

      ## PRINT ERROR MESSAGE FROM RANCH


   def finish(self):
      """
      Overrides Executor method.
      Write more....
      """
      
      ### Retrieve models created as PDBModels
      m_paths = [self.dir_models + '/' + f for f in os.listdir(
         self.dir_models)]
      self.result = [Ranch.extract_embedded(B.PDBModel(m), self.embedded) for m in m_paths]


   def cleanup(self):
      """
      Delete temporary files
      """
      if not self.debug:
         t.tryRemove(self.tempdir, tree=True)

      super().cleanup() # I think this ultimately does the same as previous line




#############
##  TESTING        
#############
import biskit.test as BT

class TestRanch(BT.BiskitTest):
   """Test class"""

   TAGS = [ BT.EXE, BT.LONG ]

   ## Write tests for each case in the ranch examples folder

   def test_pdbmodels_saved(self):

      # Create PDBModels from pdb files
      dom1 = B.PDBModel(
         "/Users/guzmanfj/Documents/Stefan/multiprot/ranch_examples/1/2z6o_mod.pdb")
      
      dom2 = B.PDBModel(
         "/Users/guzmanfj/Documents/Stefan/multiprot/ranch_examples/1/Histone_H3.pdb")
      
      domAB1 = B.PDBModel(
         "/Users/guzmanfj/Documents/Stefan/multiprot/ranch_examples/4/dom1_AB.pdb")
      
      domAB2 = domAB1.clone()
      
      # Call ranch for exmaple 1 in ranch_examples
      call_example1 = Ranch(dom1, 'GGGGGGGGGG', dom2)
      models1 = call_example1.run()
      
      # Call ranch for example 4 in ranch_examples
      call_example4 = Ranch(domAB1, 'GGGGGGGGGG', domAB2, 
         chains = {domAB1:'A', domAB2:'B'})
      models2 = call_example4.run()

      # example 5 in ranch_examples
      call_example5 = Ranch(domAB1, 'GGGGGGGGGG', domAB2, 
         chains = {domAB1:'A', domAB2:'B'}, symmetry='p2', symtemplate=domAB1)
      models3 = call_example5.run()

      # models lists contain 10 elements
      self.assertTrue(len(models1)==10, "models1 does not contain 10 elements")
      self.assertTrue(len(models2)==10, "models2 does not contain 10 elements")
      self.assertTrue(len(models3)==10, "models3 does not contain 10 elements")
      
      # elements of models lists are PDBModels
      self.assertTrue(isinstance(models1[0], B.PDBModel), 
         "models1 contents are not PDBModels")
      self.assertTrue(isinstance(models2[0], B.PDBModel), 
         "models2 contents are not PDBModels")
      self.assertTrue(isinstance(models3[0], B.PDBModel), 
         "models1 contents are not PDBModels")



class TestCleaning(BT.BiskitTest):
   """ Test class for the cleaning methods post-run """

   trimer = B.PDBModel(
      '/Users/guzmanfj/Documents/Stefan/multiprot/ranch_examples/trimer_multich/2ei4.pdb')
   chain = trimer.takeChains([1])
   domAB = B.PDBModel(
      "/Users/guzmanfj/Documents/Stefan/multiprot/ranch_examples/4/dom1_AB.pdb")


   def test_extract_fixed(self):
      """
      Test extract_fixed() method, extracting a single chain from the
      """

      # Extract single chain from trimer
      ext_test = Ranch.extract_fixed(self.chain,self.trimer)
      ext = self.trimer.takeChains([0,2])
      
      self.assertTrue(N.all(ext.xyz == ext_test.xyz))

   def test_extract_embedded(self):
      embedded = B.PDBModel(
         "/Users/guzmanfj/Documents/Stefan/multiprot/ranch_examples/4.1/models/00001eom.pdb")

      chainA = self.domAB.takeChains([0])
      embdict = {chainA:2, chainA:478}

      ext = B.PDBModel(
         "/Users/guzmanfj/Documents/Stefan/multiprot/ranch_examples/4.1/models/00001eom_mod_fixed.pdb")

      ext_test = Ranch.extract_embedded(embedded, embdict)

      self.assertTrue(N.all(ext.xyz == ext_test.xyz))

   def test_embed(self):

      emb = B.PDBModel(
         "/Users/guzmanfj/Documents/Stefan/multiprot/ranch_examples/4.1/domA_mod.pdb")

      emb_test = Ranch.embed(self.domAB.takeChains([0]), self.domAB.takeChains([1]))

      self.assertTrue(N.all(self.emb.xyz == emb_test.xyz))


if __name__ == '__main__':

   BT.localTest(debug=False)